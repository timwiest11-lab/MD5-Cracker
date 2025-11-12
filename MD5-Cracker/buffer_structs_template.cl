/*
    Buffer structs and helpers for hashing (MD5 variant: 32-bit words).
    MIT License
*/

#define DEBUG 0

// ----------------- helpers -----------------
#define ceilDiv(n,d) (((n) + (d) - 1) / (d))

// ----------------- word size -----------------
// If wordSize not provided, default to 4 (MD5 uses 32-bit words)
#ifndef wordSize
#  define wordSize 4
#endif

#if wordSize == 4
    #define word uint

    // Optional byte swap helper used by some kernels
    inline uint SWAP (uint val)
    {
        // 0xAABBCCDD -> 0xDDCCBBAA
        return (rotate(((val) & 0x00FF00FFu), 24u) | rotate(((val) & 0xFF00FF00u), 8u));
    }
#elif wordSize == 8
    #define word ulong
    #define rotl64(a,n) (rotate ((a), (n)))
    #define rotr64(a,n) (rotate ((a), (64ul-(n))))
    inline ulong SWAP (const ulong val)
    {
        ulong tmp = (rotr64(val & 0x0000FFFF0000FFFFUL, 16UL) | rotl64(val & 0xFFFF0000FFFF0000UL, 16UL));
        return (rotr64(tmp & 0xFF00FF00FF00FF00UL, 8UL) | rotl64(tmp & 0x00FF00FF00FF00FFUL, 8UL));
    }
#else
    #error "Unsupported wordSize. Use 4 (uint) or 8 (ulong)."
#endif

// ----------------- buffer sizes -----------------
// Respect external -D defines; otherwise provide MD5 defaults.
#ifndef inBufferSize
    // MD5 processes 64-byte blocks; we use enough input space in words.
    // Default: 64 bytes => 16 words of 32-bit
    #define inBufferSize (ceilDiv(64, wordSize))
#endif

#ifndef outBufferSize
    // MD5 digest is 16 bytes => 4 words of 32-bit
    #define outBufferSize (ceilDiv(16, wordSize))
#endif

#ifndef pwdBufferSize
    // Not used for plain MD5; keep 0 words
    #define pwdBufferSize 0
#endif

#ifndef saltBufferSize
    // Not used for plain MD5; keep 0 words
    #define saltBufferSize 0
#endif

#ifndef ctBufferSize
    // Not used for plain MD5; keep 0 words
    #define ctBufferSize 0
#endif

// Block/digest sizes (words), useful if kernels rely on them
#if wordSize == 4
    #ifndef hashBlockSize_int32
    #  define hashBlockSize_int32 (ceilDiv(64, wordSize))
    #endif
    #ifndef hashDigestSize_int32
    #  define hashDigestSize_int32 (ceilDiv(16, wordSize))
    #endif
#else
    #ifndef hashBlockSize_long64
    #  define hashBlockSize_long64 (ceilDiv(128, wordSize))
    #endif
    #ifndef hashDigestSize_long64
    #  define hashDigestSize_long64 (ceilDiv(64, wordSize))
    #endif
#endif

// ----------------- structs -----------------
typedef struct {
    word length;               // in bytes
    word buffer[inBufferSize]; // input buffer
} inbuf;

typedef struct {
    word buffer[outBufferSize]; // digest
} outbuf;

// Unused in plain MD5, kept for compatibility
typedef struct {
    word length; // in bytes
    word buffer[saltBufferSize];
} saltbuf;

typedef struct {
    word length; // in bytes
    word buffer[pwdBufferSize];
} pwdbuf;

typedef struct {
    word length; // in bytes
    word buffer[ctBufferSize];
} ctbuf;

// ----------------- debug helpers -----------------
#if DEBUG
    #define mod(x,y) ((x)-((x)/(y)*(y)))
    #define def_printFromWord(tag, funcName, end)               \
    static void funcName(tag const word *arr, const uint len_bytes, const bool hex)\
    {                                           \
        for (uint j = 0; j < len_bytes; j++){   \
            word v = arr[j / wordSize];         \
            word r = mod(j,wordSize) * 8;       \
            v = (v >> r) & 0xFF;                \
            if (hex) {                          \
                printf("%02x", (uint)v);        \
            } else {                            \
                printf("%c", (char)v);          \
            }                                   \
        }                                       \
        printf(end);                            \
    }
    def_printFromWord(__private, printFromWord, "")
    def_printFromWord(__global,  printFromWord_glbl, "")
    def_printFromWord(__private, printFromWord_n, "\n")
    def_printFromWord(__global,  printFromWord_glbl_n, "\n")
#endif
