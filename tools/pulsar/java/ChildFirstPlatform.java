package pulsar.harness;

import java.io.File;
import java.io.IOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.ArrayList;
import java.util.List;

import org.skepsun.kototoro.core.source.SourcePreferenceStore;
import org.skepsun.kototoro.desktop.compat.MihonDesktopPlatform;
import org.skepsun.kototoro.source.host.SourceHostPreferenceUiPlatform;

/**
 * Yerel harness köprüsü.
 *
 * Kototoro'nun masaüstü host'u eklenti JAR'ını parent-first bir URLClassLoader ile açar.
 * Host kendi yeni parser API'sini (`MangaSource` arayüzü) taşıdığı için, eklentinin
 * paketlediği eski API (`MangaParserSource`) parent'tan çözülür ve engine kaynakları
 * `NoSuchMethodError` ile düşer. Cihazda eklenti child-first yüklendiği için sorun çıkmaz.
 *
 * Bu sınıf, platformun döndürdüğü sınıf yükleyicisini yalnız
 * `org.koitharu.kotatsu.parsers.*` için child-first yapan bir sarmalayıcıya çevirir;
 * böylece eklentinin kendi parser kopyası kullanılır ve engine kaynakları yerelde de koşar.
 */
public final class ChildFirstPlatform implements SourceHostPreferenceUiPlatform {

    private static final String PARSER_PREFIX = "org.koitharu.kotatsu.parsers.";
    private static final String ENGINE_JAR_PROPERTY = "pulsar.engineJar";
    private static final String PARSERS_JAR_PROPERTY = "pulsar.parsersJar";

    private final MihonDesktopPlatform delegate = new MihonDesktopPlatform(null, null, false, null, null);

    @Override
    public ClassLoader initialize() {
        return wrap(delegate.initialize());
    }

    @Override
    public ClassLoader initialize(SourcePreferenceStore preferences) {
        return wrap(delegate.initialize(preferences));
    }

    @Override
    public Object preferenceContext() {
        return delegate.preferenceContext();
    }

    @Override
    public void close() throws IOException {
        delegate.close();
    }

    private static ClassLoader wrap(ClassLoader parent) {
        String jar = System.getProperty(ENGINE_JAR_PROPERTY);
        if (jar == null || jar.isBlank()) {
            return parent;
        }
        try {
            List<URL> urls = new ArrayList<>();
            // APK'nın dex'ten çevrilmiş JAR'ı, arayüz varsayılan metotlarını
            // `Methodref` olarak taşır ve masaüstü JVM'de ICCE verir. Maven
            // artefaktı aynı kaynağın JVM bayt kodudur; varsa önce o kullanılır.
            String parsersJar = System.getProperty(PARSERS_JAR_PROPERTY);
            if (parsersJar != null && !parsersJar.isBlank()) {
                urls.add(new File(parsersJar).toURI().toURL());
            }
            urls.add(new File(jar).toURI().toURL());
            return new ParserFirstLoader(urls.toArray(new URL[0]), parent);
        } catch (MalformedURLException error) {
            throw new IllegalStateException("engine JAR yolu geçersiz: " + jar, error);
        }
    }

    private static final class ParserFirstLoader extends URLClassLoader {

        ParserFirstLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
            if (name.startsWith(PARSER_PREFIX)) {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> loaded = findLoadedClass(name);
                    if (loaded == null) {
                        try {
                            loaded = findClass(name);
                        } catch (ClassNotFoundException ignored) {
                            // Eklentide yoksa host'un sürümüne düş.
                        }
                    }
                    if (loaded != null) {
                        if (resolve) {
                            resolveClass(loaded);
                        }
                        return loaded;
                    }
                }
            }
            // JAR'ı genel sınıf yoluna KOYMA: giriş sınıfı (PulsarSourceFactory)
            // bu yükleyici tarafından yüklenirse host INVALID_ARCHIVE verir.
            return getParent().loadClass(name);
        }
    }
}
