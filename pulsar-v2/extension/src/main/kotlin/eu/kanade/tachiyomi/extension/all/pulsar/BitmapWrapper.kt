package eu.kanade.tachiyomi.extension.all.pulsar

import android.graphics.Canvas
import org.koitharu.kotatsu.parsers.bitmap.Bitmap
import org.koitharu.kotatsu.parsers.bitmap.Rect
import java.io.OutputStream
import android.graphics.Bitmap as AndroidBitmap
import android.graphics.Rect as AndroidRect

/**
 * kotatsu-parsers'ın Bitmap arayüzünün Android karşılığı — karıştırılmış
 * sayfa grid'ini (örn. MangaFire) parser'ın drawBitmap ile yeniden
 * birleştirebilmesi için. Mihon eklentisi Android'de çalıştığından
 * android.graphics.Bitmap üzerine ince bir sarmalayıcı yeterlidir.
 */
class BitmapWrapper private constructor(
    private val androidBitmap: AndroidBitmap,
) : Bitmap, AutoCloseable {

    private val canvas by lazy { Canvas(androidBitmap) }

    override val height: Int get() = androidBitmap.height
    override val width: Int get() = androidBitmap.width

    override fun drawBitmap(sourceBitmap: Bitmap, src: Rect, dst: Rect) {
        val android = (sourceBitmap as BitmapWrapper).androidBitmap
        canvas.drawBitmap(android, src.toAndroidRect(), dst.toAndroidRect(), null)
    }

    override fun close() = androidBitmap.recycle()

    fun compressTo(output: OutputStream) {
        androidBitmap.compress(AndroidBitmap.CompressFormat.JPEG, 90, output)
    }

    companion object {
        fun create(width: Int, height: Int) =
            BitmapWrapper(AndroidBitmap.createBitmap(width, height, AndroidBitmap.Config.ARGB_8888))

        fun create(bitmap: AndroidBitmap) =
            BitmapWrapper(if (bitmap.isMutable) bitmap else bitmap.copy(AndroidBitmap.Config.ARGB_8888, true))

        private fun Rect.toAndroidRect() = AndroidRect(left, top, right, bottom)
    }
}
