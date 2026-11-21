package eu.kanade.tachiyomi.extension.all.pulsar

import org.mozilla.javascript.ClassShutter
import org.mozilla.javascript.Context
import org.mozilla.javascript.ContextFactory
import org.mozilla.javascript.NativeJSON
import org.mozilla.javascript.Undefined

// Sayfa listesini hesaplayan küçük JS ifadelerini çalıştırır (Rhino, yorumlayıcı mod).
//
// Amaç tarayıcı taklidi DEĞİL: sayfadaki `/g/<id>/` + n, atob(...), şablon birleştirme
// gibi hesaplar. Bu yüzden DOM/fetch yoktur; script yalnız verilen değişkenlerle
// (html, url, baseUrl) hesap yapar ve son ifadesini döndürür. Sonuç JSON dizisi ise
// JSON metnine çevrilir, düz metinse aynen döner.
//
// Güvenlik: ClassShutter hiçbir Java sınıfını görünür kılmaz (Packages/java kapalı);
// komut sayacı ve duvar saati sınırı sonsuz döngüyü keser. Hata asla dışarı sızmaz:
// her başarısızlık null'dur, çağıran diğer yollara devam eder.
internal object PulsarJs {
    // ~2 milyon yorumlanmış komut: normal ifadeler için bol, sonsuz döngü için kısa.
    private const val INSTRUCTION_LIMIT = 2_000_000

    // Sayaç her bu kadar komutta bir observer'a bildirilir; kesme bu aralıkta olur.
    private const val OBSERVE_EVERY = 50_000

    fun eval(script: String, vars: Map<String, String>, timeoutMs: Int = 800): String? =
        runCatching<String?> {
            if (script.isBlank()) return@runCatching null
            val factory = SandboxFactory(timeoutMs.coerceAtLeast(1))
            val cx = factory.enterContext()
            try {
                val scope = cx.initStandardObjects()
                // html/url/baseUrl global değişken olarak verilir.
                for ((name, value) in vars) scope.put(name, scope, value)
                val result = cx.evaluateString(scope, script, "pulsar-page", 1, null)
                when {
                    result == null || result === Undefined.instance -> null
                    result is CharSequence -> result.toString().ifBlank { null }
                    // Dizi de nesne de JSON'a çevrilir; sayı/boolean metne düşer.
                    else -> NativeJSON.stringify(cx, scope, result, null, null)?.toString()
                        ?.ifBlank { null }
                }
            } finally {
                Context.exit()
            }
        }.getOrNull()

    // Her eval çağrısı kendi fabrikasını kurar: sayaç ve süre durumu çağrıya özeldir,
    // eşzamanlı iki çalıştırma birbirinin sınırını tüketmez.
    private class SandboxFactory(private val timeoutMs: Int) : ContextFactory() {
        private var executed = 0L
        private val deadline = System.nanoTime() + timeoutMs * 1_000_000L

        override fun makeContext(): Context {
            val cx = super.makeContext()
            // Android'de bytecode üretimi yok; optimize edilmiş mod desteklenmez.
            cx.optimizationLevel = -1
            cx.languageVersion = Context.VERSION_ES6
            // Hiçbir Java sınıfı script'e görünmez: Packages/java erişimi kapalı.
            cx.setClassShutter(object : ClassShutter {
                override fun visibleToScripts(fullClassName: String): Boolean = false
            })
            cx.instructionObserverThreshold = OBSERVE_EVERY
            return cx
        }

        override fun observeInstructionCount(cx: Context, instructionCount: Int) {
            executed += instructionCount
            if (executed > INSTRUCTION_LIMIT || System.nanoTime() > deadline) {
                // Rhino'nun beklediği kesme biçimi: Error yorumlayıcıyı hemen durdurur.
                throw Error("pulsar-js: komut/süre sınırı aşıldı")
            }
        }
    }
}
