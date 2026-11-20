package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import java.io.OutputStream
import java.net.InetAddress
import java.net.Socket
import javax.net.ssl.SSLSocketFactory

/**
 * DPI (SNI) atlatma: TLS ClientHello'yu küçük parçalara bölerek gönderir.
 *
 * Neden: bazı ISP'ler TCP bağlantısını kesmez, TLS handshake'in ilk kaydındaki
 * SNI alanına bakıp bağlantıyı sıfırlar (RST). ClientHello tek yazımda giderse
 * DPI paketi bütün olarak görür; 1-N baytlık parçalara bölünüp aralıklı
 * gönderildiğinde SNI çoğu zaman okunamaz (zapret/GoodbyeDPI'ın kullanıcı-alanı eşi).
 *
 * Sınır: VPN değildir; yalnız TLS el sıkışmasının ilk yazımını böler. TCP/IP
 * seviyesinde (ör. Cloudflare IP'lerine) engel varsa işe yaramaz.
 */
internal class TlsFragmentingSocketFactory(private val split: Int) : SSLSocketFactory() {

    private val base: SSLSocketFactory =
        SSLSocketFactory.getDefault() as SSLSocketFactory

    override fun getDefaultCipherSuites(): Array<String> = base.defaultCipherSuites

    override fun getSupportedCipherSuites(): Array<String> = base.supportedCipherSuites

    // OkHttp bu imzayı kullanır: ham soket elimize geçer, TLS'i onun üstünde açar.
    override fun createSocket(s: Socket, host: String, port: Int, autoClose: Boolean): Socket =
        base.createSocket(FragmentingSocket(s, split), host, port, autoClose)

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
}

/** Ham soketi sarmalar; yalnız çıkış akışının İLK yazımını böler. */
private class FragmentingSocket(private val inner: Socket, private val split: Int) : Socket() {

    private val fragmentingOut by lazy { FragmentingOutputStream(inner.getOutputStream(), split) }

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
    private val split: Int,
) : OutputStream() {

    private var firstWrite = true

    override fun write(b: Int) {
        inner.write(b)
        firstWrite = false
    }

    override fun write(b: ByteArray, off: Int, len: Int) {
        if (!firstWrite || len <= split) {
            inner.write(b, off, len)
            firstWrite = false
            return
        }
        // ClientHello'yu iki parçada gönder: SNI tek pakette görünmesin.
        inner.write(b, off, split)
        inner.flush()
        Thread.sleep(20L)
        inner.write(b, off + split, len - split)
        firstWrite = false
    }

    override fun flush() = inner.flush()
    override fun close() = inner.close()
}
