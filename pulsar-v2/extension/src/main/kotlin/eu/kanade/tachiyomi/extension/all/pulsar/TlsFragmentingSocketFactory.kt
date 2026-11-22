package eu.kanade.tachiyomi.extension.all.pulsar

import java.io.OutputStream
import java.net.InetAddress
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ThreadLocalRandom
import javax.net.ssl.SSLSocketFactory

/**
 * DPI (SNI) atlatma: TLS ClientHello'yu küçük parçalara bölerek gönderir.
 *
 * Neden: bazı ISP'ler TCP bağlantısını kesmez, TLS handshake'in ilk kaydındaki
 * SNI alanına bakıp bağlantıyı sıfırlar (RST). ClientHello tek yazımda giderse
 * DPI paketi bütün olarak görür; parçalara bölünüp aralıklı gönderildiğinde SNI
 * çoğu zaman okunamaz (zapret/GoodbyeDPI'ın kullanıcı-alanı eşi).
 *
 * BİLİNÇLİ DAVRANIŞ DEĞİŞİKLİĞİ: eski sürüm ilk yazımı yalnız `split` baytta
 * bölüyordu. Tek baytlık bölme bazı sunucu/ara katmanlarda yeniden birleştirilip
 * yakalanıyordu; GoodbyeDPI'ın çalışan profili (-1) ve `-e 2` ClientHello'yu
 * ikiye böler. Bu yüzden varsayılan parçalar `[1, 2]` oldu (1 bayt, 5-25 ms
 * jitter, 2 bayt, jitter, geri kalan). Ayarlanabilir: `tlsFragmentSizes`
 * ("1,2"; en fazla 4 parça, her parça 1-64 bayt), `tlsFragmentDelay`
 * (ms, varsayılan 10, 0-100; 0 gecikmeyi kapatır).
 *
 * Sınır: VPN değildir; yalnız TLS el sıkışmasının ilk yazımını böler. TCP/IP
 * seviyesinde (ör. Cloudflare IP'lerine) engel varsa işe yaramaz.
 */
internal class TlsFragmentingSocketFactory(
    fragmentSizes: IntArray = intArrayOf(1, 2),
    private val delayMs: Int = DEFAULT_FRAGMENT_DELAY_MS,
) : SSLSocketFactory() {

    private val fragmentSizes: IntArray = fragmentSizes.copyOf()

    private val base: SSLSocketFactory =
        SSLSocketFactory.getDefault() as SSLSocketFactory

    override fun getDefaultCipherSuites(): Array<String> = base.defaultCipherSuites

    override fun getSupportedCipherSuites(): Array<String> = base.supportedCipherSuites

    // OkHttp bu imzayı kullanır: ham soket elimize geçer, TLS'i onun üstünde açar.
    override fun createSocket(s: Socket, host: String, port: Int, autoClose: Boolean): Socket =
        base.createSocket(FragmentingSocket(s, fragmentSizes, delayMs), host, port, autoClose)

    override fun createSocket(host: String, port: Int): Socket = base.createSocket(host, port)

    override fun createSocket(
        host: String,
        port: Int,
        localHost: InetAddress,
        localPort: Int,
    ): Socket = base.createSocket(host, port, localHost, localPort)

    override fun createSocket(host: InetAddress, port: Int): Socket = base.createSocket(host, port)

    override fun createSocket(
        address: InetAddress,
        port: Int,
        localAddress: InetAddress,
        localPort: Int,
    ): Socket = base.createSocket(address, port, localAddress, localPort)

    internal companion object {
        /** Varsayılan: 1 + 2 bayt (GoodbyeDPI `-1` / `-e 2` deseni). */
        val DEFAULT_FRAGMENT_SIZES: IntArray get() = intArrayOf(1, 2)

        /** Parçalar arası taban bekleme; 0 gecikmeyi kapatır. */
        const val DEFAULT_FRAGMENT_DELAY_MS = 10

        const val MAX_FRAGMENTS = 4
        const val MAX_FRAGMENT_SIZE = 64

        /**
         * "1,2" gibi virgüllü listeyi parça boyutlarına çevirir. Geçersiz
         * değerler atlanır; hiç geçerli değer yoksa varsayılan `[1, 2]`.
         */
        fun parseFragmentSizes(raw: String?): IntArray {
            val parsed = raw.orEmpty()
                .split(',')
                .mapNotNull { it.trim().toIntOrNull() }
                .filter { it in 1..MAX_FRAGMENT_SIZE }
                .take(MAX_FRAGMENTS)
                .toIntArray()
            return if (parsed.isEmpty()) DEFAULT_FRAGMENT_SIZES else parsed
        }
    }
}

/**
 * Bir host TLS'te (reset / trust-anchor) sıfırlandıysa 30 dk boyunca doğrudan
 * parçalı istemciden geçirir. Böylece her istekte önce düz deneme yapılmaz.
 * Kayıt bellekte ve sürelidir; süreç/eklenti sınıf yükleyici ömrü boyunca yaşar.
 */
internal object TlsFragmentSticky {
    private const val TTL_MS = 30L * 60L * 1000L

    private val hosts = ConcurrentHashMap<String, Long>()

    fun isSticky(host: String): Boolean {
        val expiresAt = hosts[host] ?: return false
        if (expiresAt <= System.currentTimeMillis()) {
            hosts.remove(host, expiresAt)
            return false
        }
        return true
    }

    fun mark(host: String) {
        hosts[host] = System.currentTimeMillis() + TTL_MS
    }
}

/** Ham soketi sarmalar; yalnız çıkış akışının İLK yazımını böler. */
private class FragmentingSocket(
    private val inner: Socket,
    private val fragmentSizes: IntArray,
    private val delayMs: Int,
) : Socket() {

    private val fragmentingOut by lazy {
        FragmentingOutputStream(inner.getOutputStream(), fragmentSizes, delayMs)
    }

    override fun getOutputStream(): OutputStream = fragmentingOut

    override fun getInputStream() = inner.getInputStream()
    override fun close() = inner.close()
    override fun isClosed(): Boolean = inner.isClosed
    override fun isConnected(): Boolean = inner.isConnected
    override fun isBound(): Boolean = inner.isBound
    override fun getSoTimeout(): Int = inner.soTimeout
    override fun setSoTimeout(timeout: Int) { inner.soTimeout = timeout }
    override fun getTcpNoDelay(): Boolean = inner.tcpNoDelay
    override fun setTcpNoDelay(on: Boolean) { inner.tcpNoDelay = on }
    override fun getKeepAlive(): Boolean = inner.keepAlive
    override fun setKeepAlive(on: Boolean) { inner.keepAlive = on }
    override fun getSoLinger(): Int = inner.soLinger
    override fun setSoLinger(on: Boolean, linger: Int) { inner.setSoLinger(on, linger) }
    override fun getLocalAddress(): InetAddress = inner.localAddress
    override fun getLocalPort(): Int = inner.localPort
    override fun getInetAddress(): InetAddress = inner.inetAddress
    override fun getPort(): Int = inner.port
    override fun shutdownOutput() = inner.shutdownOutput()
    override fun shutdownInput() = inner.shutdownInput()
}

private class FragmentingOutputStream(
    private val inner: OutputStream,
    private val fragmentSizes: IntArray,
    private val delayMs: Int,
) : OutputStream() {

    private var firstWrite = true

    override fun write(b: Int) {
        inner.write(b)
        firstWrite = false
    }

    override fun write(b: ByteArray, off: Int, len: Int) {
        if (len <= 0) return
        if (!firstWrite) {
            inner.write(b, off, len)
            return
        }
        firstWrite = false

        // İlk yazım (ClientHello) parçaların toplamından küçükse bölmek anlamsız.
        if (len <= fragmentSizes.sum()) {
            inner.write(b, off, len)
            inner.flush()
            return
        }

        // 1 bayt, jitter, 2 bayt, jitter, geri kalan: SNI tek pakette görünmesin.
        var pos = off
        var remaining = len
        for (size in fragmentSizes) {
            if (remaining <= 0) break
            val take = minOf(size, remaining)
            inner.write(b, pos, take)
            inner.flush()
            pos += take
            remaining -= take
            if (remaining > 0) {
                val pause = nextPauseMs()
                if (pause > 0) Thread.sleep(pause)
            }
        }
        if (remaining > 0) {
            inner.write(b, pos, remaining)
            inner.flush()
        }
    }

    /** Taban `delayMs` ± jitter; varsayılan 10 ms → 5-25 ms. */
    private fun nextPauseMs(): Long {
        if (delayMs <= 0) return 0L
        val jitter = ThreadLocalRandom.current().nextInt(-5, 16)
        return (delayMs + jitter).coerceAtLeast(1).toLong()
    }

    override fun flush() = inner.flush()
    override fun close() = inner.close()
}
