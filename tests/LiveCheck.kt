package org.koitharu.kotatsu.parsers

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.jupiter.api.Test
import org.koitharu.kotatsu.parsers.model.Manga
import org.koitharu.kotatsu.parsers.model.MangaChapter
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.model.search.MangaSearchQuery
import org.koitharu.kotatsu.parsers.util.mimeType
import java.io.File
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/**
 * Pulsar: her kaynağı gerçek parser ile uçtan uca dener (liste -> detay -> bölüm -> sayfa -> görsel)
 * ve sonucu LIVE_OUT dosyasına JSON olarak yazar. Asla fail etmez; sonuç dosyası hakemdir.
 *
 * LIVE_OUT   : çıktı dosyası (varsayılan build/live-results.json)
 * LIVE_ONLY  : virgülle ayrılmış kaynak adları (boş = hepsi)
 * LIVE_PARALLEL : eşzamanlı kaynak sayısı (varsayılan 4)
 */
internal class LiveCheck {

	@Test
	fun run() {
		val out = File(System.getenv("LIVE_OUT") ?: "build/live-results.json")
		val only = System.getenv("LIVE_ONLY")?.split(',')?.map { it.trim() }?.filter { it.isNotEmpty() }?.toSet()
		val parallel = System.getenv("LIVE_PARALLEL")?.toIntOrNull()?.coerceIn(1, 16) ?: 4
		val results = runBlocking(Dispatchers.IO) {
			val gate = Semaphore(parallel)
			MangaParserSource.entries
				.filter { only.isNullOrEmpty() || it.name in only }
				.map { source -> async { gate.withPermit { check(source) } } }
				.awaitAll()
		}
		out.absoluteFile.parentFile?.mkdirs()
		out.writeText(JSONArray(results).toString(1))
		val ok = results.count { it.optBoolean("ok") }
		println("LIVECHECK ${results.size} kaynak, $ok başarılı")
	}

	private suspend fun check(source: MangaParserSource): JSONObject {
		val started = System.currentTimeMillis()
		val result = JSONObject().put("id", source.name).put("name", source.title)
		var stage = "init"
		try {
			val parser = MangaLoaderContextMock.newParserInstance(source)
			result.put("domain", parser.domain)

			stage = "list"
			val list = withTimeout(STAGE_TIMEOUT) { parser.getList(MangaSearchQuery.EMPTY) }
			result.put("list", list.size)
			if (list.isEmpty()) return done(result, started, "list", "empty", "Liste boş döndü")

			stage = "details"
			var chapters: List<MangaChapter> = emptyList()
			for (manga in list.take(3)) {
				val details: Manga = withTimeout(STAGE_TIMEOUT) { parser.getDetails(manga) }
				chapters = details.chapters.orEmpty()
				if (chapters.isNotEmpty()) break
			}
			result.put("chapters", chapters.size)
			if (chapters.isEmpty()) return done(result, started, "details", "empty", "İlk 3 mangada bölüm yok")

			stage = "pages"
			var pages = withTimeout(STAGE_TIMEOUT) { parser.getPages(chapters.last()) }
			if (pages.isEmpty() && chapters.size > 1) {
				pages = withTimeout(STAGE_TIMEOUT) { parser.getPages(chapters.first()) }
			}
			result.put("pages", pages.size)
			if (pages.isEmpty()) return done(result, started, "pages", "empty", "Bölümde sayfa yok")

			stage = "image"
			val url = parser.getPageUrl(pages.first())
			withTimeout(STAGE_TIMEOUT) {
				MangaLoaderContextMock.doRequest(url, source).use {
					if (!it.isSuccessful) throw IllegalStateException("HTTP ${it.code} görsel: $url")
					val mime = it.mimeType.orEmpty()
					if (!mime.startsWith("image/")) throw IllegalStateException("Görsel değil ($mime): $url")
				}
			}
			result.put("ok", true).put("stage", "image")
			result.put("ms", System.currentTimeMillis() - started)
			return result
		} catch (e: Throwable) {
			return done(result, started, stage, classify(e), (e.message ?: e.toString()).take(300))
		}
	}

	private fun done(result: JSONObject, started: Long, stage: String, errorClass: String, message: String): JSONObject {
		result.put("ok", false).put("stage", stage).put("error_class", errorClass).put("error", message)
		result.put("ms", System.currentTimeMillis() - started)
		return result
	}

	private fun classify(e: Throwable): String {
		if (Regex("""\b429\b""").containsMatchIn(e.message.orEmpty())) return "rate_limit"
		var cause: Throwable? = e
		while (cause != null) {
			val name = cause.javaClass.simpleName
			when {
				name == "CloudFlareProtectedException" -> return "cloudflare"
				cause is UnknownHostException -> return "dns"
				cause is SSLException -> return "ssl"
				cause is SocketTimeoutException || name == "TimeoutCancellationException" -> return "timeout"
				cause is ConnectException -> return "connect"
				name.contains("HttpStatus") -> return "http"
			}
			cause = cause.cause?.takeIf { it !== cause }
		}
		val msg = e.message.orEmpty()
		return when {
			msg.contains("Cannot decode image") -> "decode" // CI sahte bağlamı webp vb. çözemez; cihazda sorun değil
			Regex("""\b429\b""").containsMatchIn(msg) -> "rate_limit"
			Regex("""\b(403|429|503)\b""").containsMatchIn(msg) -> "http_blocked"
			Regex("""\b(404|410)\b""").containsMatchIn(msg) -> "http_gone"
			Regex("""\b5\d\d\b""").containsMatchIn(msg) -> "http_5xx"
			else -> "parse"
		}
	}

	private companion object {
		const val STAGE_TIMEOUT = 75_000L
	}
}
