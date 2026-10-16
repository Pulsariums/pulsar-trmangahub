package eu.kanade.tachiyomi.extension.all.pulsar

import okhttp3.Interceptor
import okhttp3.Response
import java.util.concurrent.ConcurrentHashMap

/**
 * Nyora'nın RedirectDomainMapper örüntüsü, PULSAR VERİSİYLE:
 *
 *  - PİNLEME: 03_probe_fast.py'nin OTOMATIK_TAMIR ile bulduğu eski→canlı
 *    domain eşleşmeleri derleme sırasında patches.json'a yazılır; fabrika
 *    bunları istek seviyesinde sabitler. Ölmüş domaine giden her istek,
 *    ölü ilk atağı atlayarak doğrudan canlı hosta yöner.
 *  - ÖĞRENME: sunucunun GERÇEKTEN izlediği 3xx yönlendirmelerini dinle;
 *    eski→canlı eşleşmeyi kalıcı hafızaya yaz, tüm kaynaklarla paylaş.
 *    (Nyora'nın bu kısmı ba-vuru hardcoded tabloya güvenmez; biz de
 *    güvenmiyoruz — tablo sadece hızlı başlangıç.)
 *
 * Süreç-geneli: bir kaynağın öğrendiği host her kaynak tarafından kullanılır.
 */
object RedirectDomainMapper : Interceptor {

    private val liveHost = ConcurrentHashMap<String, String>()

    fun pin(oldHost: String, newHost: String) {
        if (oldHost.isNotBlank() && newHost.isNotBlank() && oldHost != newHost) {
            liveHost[oldHost] = newHost
            liveHost[oldHost.removePrefix("www.")] = newHost
            liveHost["www.$oldHost"] = newHost
        }
    }

    override fun intercept(chain: Interceptor.Chain): Response {
        var request = chain.request()
        val requestedHost = request.url.host
        liveHost[requestedHost]?.takeIf { it != requestedHost }?.let { mapped ->
            request = request.newBuilder()
                .url(request.url.newBuilder().host(mapped).build())
                .build()
        }

        val response = chain.proceed(request)

        val sentHost = request.url.host
        val finalHost = response.request.url.host
        if (finalHost.isNotEmpty() && finalHost != sentHost) {
            liveHost[sentHost] = finalHost
            liveHost[requestedHost] = finalHost
        }
        return response
    }
}
