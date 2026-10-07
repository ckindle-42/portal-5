/* Fixture for the binary_similarity probe (EmbeddingGemma 2 consumer measurement).
 * provenance: authored by Claude Sonnet 5.5 in session 018aJ1P8 on 2026-10-07 - 24 small
 * self-contained functions with distinct behaviour; each is compiled at -O0 and -O2 by the probe
 * and matched across optimisation levels. Never called; compiled with -c only. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

int f_sum_array(const int *a, size_t n) { int s = 0; for (size_t i = 0; i < n; i++) s += a[i]; return s; }
int f_max_array(const int *a, size_t n) { int m = a[0]; for (size_t i = 1; i < n; i++) if (a[i] > m) m = a[i]; return m; }
uint32_t f_crc32_byte(uint32_t crc, uint8_t b) { crc ^= b; for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1)); return crc; }
size_t f_strlen_custom(const char *s) { size_t n = 0; while (s[n]) n++; return n; }
int f_strcmp_custom(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return (unsigned char)*a - (unsigned char)*b; }
void f_reverse_bytes(uint8_t *p, size_t n) { for (size_t i = 0; i < n / 2; i++) { uint8_t t = p[i]; p[i] = p[n - 1 - i]; p[n - 1 - i] = t; } }
uint64_t f_fib(unsigned n) { uint64_t a = 0, b = 1; for (unsigned i = 0; i < n; i++) { uint64_t t = a + b; a = b; b = t; } return a; }
uint32_t f_gcd(uint32_t a, uint32_t b) { while (b) { uint32_t t = a % b; a = b; b = t; } return a; }
int f_is_prime(uint32_t n) { if (n < 2) return 0; for (uint32_t i = 2; i * i <= n; i++) if (n % i == 0) return 0; return 1; }
uint32_t f_popcount(uint32_t x) { uint32_t c = 0; while (x) { x &= x - 1; c++; } return c; }
uint32_t f_rotl13(uint32_t x) { return (x << 13) | (x >> 19); }
void f_xor_buffer(uint8_t *d, const uint8_t *k, size_t n, size_t kn) { for (size_t i = 0; i < n; i++) d[i] ^= k[i % kn]; }
int f_binary_search(const int *a, int n, int key) { int lo = 0, hi = n - 1; while (lo <= hi) { int mid = lo + (hi - lo) / 2; if (a[mid] == key) return mid; if (a[mid] < key) lo = mid + 1; else hi = mid - 1; } return -1; }
void f_bubble_sort(int *a, int n) { for (int i = 0; i < n - 1; i++) for (int j = 0; j < n - i - 1; j++) if (a[j] > a[j + 1]) { int t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; } }
uint32_t f_hash_djb2(const char *s) { uint32_t h = 5381; int c; while ((c = (unsigned char)*s++)) h = ((h << 5) + h) + c; return h; }
int f_hex_digit(char c) { if (c >= '0' && c <= '9') return c - '0'; if (c >= 'a' && c <= 'f') return c - 'a' + 10; if (c >= 'A' && c <= 'F') return c - 'A' + 10; return -1; }
int f_atoi_custom(const char *s) { int sign = 1, v = 0; if (*s == '-') { sign = -1; s++; } while (*s >= '0' && *s <= '9') v = v * 10 + (*s++ - '0'); return sign * v; }
void f_memset_custom(void *p, int v, size_t n) { uint8_t *b = p; for (size_t i = 0; i < n; i++) b[i] = (uint8_t)v; }
int f_checksum16(const uint8_t *p, size_t n) { uint32_t s = 0; for (size_t i = 0; i + 1 < n; i += 2) s += (p[i] << 8) | p[i + 1]; while (s >> 16) s = (s & 0xFFFF) + (s >> 16); return (int)(~s & 0xFFFF); }
int f_clamp(int x, int lo, int hi) { return x < lo ? lo : (x > hi ? hi : x); }
uint32_t f_lcg_next(uint32_t *state) { *state = *state * 1664525u + 1013904223u; return *state; }
int f_count_char(const char *s, char c) { int n = 0; for (; *s; s++) if (*s == c) n++; return n; }
void f_swap_endian32(uint32_t *p, size_t n) { for (size_t i = 0; i < n; i++) { uint32_t x = p[i]; p[i] = (x >> 24) | ((x >> 8) & 0xFF00) | ((x << 8) & 0xFF0000) | (x << 24); } }
