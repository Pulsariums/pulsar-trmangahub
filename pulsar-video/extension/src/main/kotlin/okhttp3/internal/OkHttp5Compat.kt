// OkHttp 5 uyumluluk katmanı — yalnız EKSİK sembol.
//
// kototoro-parsers OkHttp 5.1.0'a derlendiği için derlenmiş bytecode'u
// `okhttp3.internal._UtilCommonKt` içindeki iki üyeyi çağırıyor:
//   - `_UtilCommonKt.toLongOrDefault(String, long)` -> OkHttpUtils.headersContentLength
//   - `_UtilCommonKt.closeQuietly(Closeable)`       -> ContinuationCallCallback
// OkHttp 4.12 host'unda bu sınıf yok: ilk HTTP çağrısında NoClassDefFoundError
// düşüyor ve parser kaynakları boş liste dönüyor. Aşağıdaki iki fonksiyon
// OkHttp 5.1.0 `-UtilCommon.kt` gövdelerinin birebir eşidir; başka sembol yok.
@file:JvmName("_UtilCommonKt")

package okhttp3.internal

import java.io.Closeable

/** OkHttp 5.1.0: `try { toLong() } catch (_: NumberFormatException) { defaultValue }` */
fun String.toLongOrDefault(defaultValue: Long): Long =
    try {
        toLong()
    } catch (_: NumberFormatException) {
        defaultValue
    }

/** OkHttp 5.1.0: RuntimeException yeniden fırlatılır, diğer Exception yutulur. */
fun Closeable.closeQuietly() {
    try {
        close()
    } catch (rethrown: RuntimeException) {
        throw rethrown
    } catch (_: Exception) {
    }
}
