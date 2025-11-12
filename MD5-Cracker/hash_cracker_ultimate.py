import pyopencl as cl
import numpy as np
import itertools
import time
import hashlib

# === Hilfsfunktion: MD5 Hex -> 4x uint32 little-endian ===
def md5_hex_to_uint4_le(hexstr):
    bs = bytes.fromhex(hexstr)
    return [
        int.from_bytes(bs[0:4],  'little'),
        int.from_bytes(bs[4:8],  'little'),
        int.from_bytes(bs[8:12], 'little'),
        int.from_bytes(bs[12:16],'little'),
    ]

# === Wortgenerator ===
def word_generator(charset, min_len, max_len):
    for length in range(min_len, max_len+1):
        for word in itertools.product(charset, repeat=length):
            yield ''.join(word)

# === GPU-Programm bauen ===
def build_program(ctx, kernel_file):
    with open(kernel_file, "r", encoding="utf-8") as f:
        src = f.read()
    return cl.Program(ctx, src).build(options=[
        "-I", ".", "-D", "hashBlockSize_int32=16", "-D", "inBufferSize=16"
    ])

# === Spinner & Statusausgabe ===
spinner_cycle = ["\\", "-", "/", "|"]

def print_status(label, checked, word, start_time, spinner_index):
    elapsed = time.time() - start_time
    hps = checked / elapsed if elapsed > 0 else 0
    spinner = spinner_cycle[spinner_index % len(spinner_cycle)]
    print(f"{label} geprüft: {checked:,} | letzter Kandidat: {word} | {int(hps):,} H/s | Zeit: {elapsed:.1f}s | {spinner}", end="\r")

# === GPU-Run mit Status ===
def run_gpu(word_gen, target_hash, kernel_file="md5.cl"):
    ctx = cl.create_some_context()
    queue = cl.CommandQueue(ctx)
    program = build_program(ctx, kernel_file)

    target_uints = md5_hex_to_uint4_le(target_hash)
    target_buf = cl.Buffer(ctx, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,
                           hostbuf=np.array(target_uints, dtype=np.uint32))

    batch_size = 100000
    candidates = []
    start_time = time.time()
    checked = 0
    spinner_index = 0

    for word in word_gen:
        candidates.append(word)
        if len(candidates) >= batch_size:
            found = process_batch(ctx, queue, program, candidates, target_buf)
            checked += len(candidates)
            print_status("GPU", checked, candidates[-1], start_time, spinner_index)
            spinner_index += 1
            candidates = []
            if found:
                print(f"\n✅ Passwort gefunden: {found}")
                return found

    if candidates:
        found = process_batch(ctx, queue, program, candidates, target_buf)
        checked += len(candidates)
        print_status("GPU", checked, candidates[-1], start_time, spinner_index)
        if found:
            print(f"\n✅ Passwort gefunden: {found}")
            return found

    print("\n❌ Kein Passwort gefunden.")
    return None

def process_batch(ctx, queue, program, candidates, target_buf):
    mf = cl.mem_flags
    all_bytes = ''.join(candidates).encode('utf-8')
    offsets, lengths = [], []
    pos = 0
    for w in candidates:
        offsets.append(pos)
        lengths.append(len(w))
        pos += len(w)

    input_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                          hostbuf=np.frombuffer(all_bytes, dtype=np.uint8))
    offsets_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                            hostbuf=np.array(offsets, dtype=np.int32))
    lengths_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                            hostbuf=np.array(lengths, dtype=np.int32))
    results_buf = cl.Buffer(ctx, mf.WRITE_ONLY, size=len(candidates)*np.int32().nbytes)

    kernel = program.hash_main_flat
    kernel(queue, (len(candidates),), None,
           input_buf, offsets_buf, lengths_buf, target_buf, results_buf)

    results = np.empty(len(candidates), dtype=np.int32)
    cl.enqueue_copy(queue, results, results_buf).wait()

    hit_indices = np.where(results == 1)[0]
    if len(hit_indices) > 0:
        return candidates[int(hit_indices[0])]
    return None

# === CPU-Run mit Status ===
def run_cpu(word_gen, target_hash, cores=4):
    start_time = time.time()
    checked = 0
    spinner_index = 0

    for word in word_gen:
        checked += 1
        h = hashlib.md5(word.encode()).hexdigest()
        if h.lower() == target_hash.lower():
            elapsed = time.time() - start_time
            print(f"\n✅ Passwort gefunden: {word} | geprüft: {checked:,} | Zeit: {elapsed:.1f}s")
            return word

        if checked % 10000 == 0:
            print_status("CPU", checked, word, start_time, spinner_index)
            spinner_index += 1

    print("\n❌ Kein Passwort gefunden.")
    return None

# === Hybrid-Run ===
def run_hybrid(word_gen, target_hash, kernel_file="md5.cl", cores=4):
    found = run_gpu(word_gen, target_hash, kernel_file)
    if not found:
        found = run_cpu(word_gen, target_hash, cores)
    return found

# === Wordlist Loader mit Encoding-Fallback ===
def load_wordlist(path="wordlist.txt"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]

# === Hauptprogramm ===
def main():
    print("🔧 HASH CRACKER mit CPU/GPU/Hybrid und Live-Status")
    mode = int(input("Modus wählen (1=CPU, 2=GPU, 3=Hybrid): "))
    attack = int(input("Angriffstyp wählen (1=Bruteforce, 2=Wordlist, 3=Hybrid): "))
    target_hash = input("Ziel-Hash (Hex): ").strip()

    word_gen = None

    # === Wordlist ===
    if attack == 2:
        wordlist = load_wordlist()
        word_gen = iter(wordlist)

    # === Bruteforce ===
    if attack == 1 or attack == 3:
        min_len = int(input("Minimale Länge: "))
        max_len = int(input("Maximale Länge: "))
        print("Zeichensatz wählen:")
        print("1 = abc...ABC...0123456789")
        print("2 = abc...ABC...0123456789?!./=")
        print("3 = Nur Zahlen (0123456789)")
        print("4 = Custom Eingabe")
        charset_choice = int(input("Option: "))

        if charset_choice == 1:
            charset = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        elif charset_choice == 2:
            charset = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ?!./=$%&"
        elif charset_choice == 3:
            charset = "0123456789"
        elif charset_choice == 4:
            charset = input("Eigener Zeichensatz: ")
        else:
            charset = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        brute_gen = word_generator(charset, min_len, max_len)

        if attack == 1:
            word_gen = brute_gen
        elif attack == 3:
            wordlist = load_wordlist()
            word_gen = iter(wordlist + list(brute_gen))

    # === Moduswahl CPU/GPU/Hybrid ===
    if mode == 1:
        cores = int(input("CPU-Kerne (max 16): "))
        run_cpu(word_gen, target_hash, cores)
    elif mode == 2:
        run_gpu(word_gen, target_hash, kernel_file="md5.cl")
    elif mode == 3:
        cores = int(input("CPU-Kerne (max 16): "))
        run_hybrid(word_gen, target_hash, kernel_file="md5.cl", cores=cores)
    else:
        print("Ungültiger Modus.")

if __name__ == "__main__":
    main()
