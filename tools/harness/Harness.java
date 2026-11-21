import java.lang.reflect.Method;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.json.JSONArray;
import org.json.JSONObject;

import eu.kanade.tachiyomi.source.CatalogueSource;
import eu.kanade.tachiyomi.source.Source;
import eu.kanade.tachiyomi.source.model.MangasPage;
import eu.kanade.tachiyomi.source.model.Page;
import eu.kanade.tachiyomi.source.model.SChapter;
import eu.kanade.tachiyomi.source.model.SManga;

import org.skepsun.kototoro.core.source.LoadedMihonExtension;
import org.skepsun.kototoro.core.source.MihonJarIdentity;
import org.skepsun.kototoro.core.source.MihonJarMetadata;
import org.skepsun.kototoro.core.source.MihonSourceDescriptor;
import org.skepsun.kototoro.desktop.compat.MihonDesktopPlatform;
import org.skepsun.kototoro.source.host.FileSourcePreferenceStore;
import org.skepsun.kototoro.source.host.MihonJarInspector;
import org.skepsun.kototoro.source.host.MihonJarRegistry;

/**
 * Kototoro masaüstü çalışma zamanıyla eklenti JAR'ını yerelde koşturur.
 *
 * Kullanım: Harness <extension.jar> <domain> [domain...]
 * Çıktı: her domain için tek satır JSON.
 *
 * Not: eklenti JAR'ı sistem sınıf yoluna KONMAZ; MihonJarRegistry onu
 * kendi URLClassLoader'ıyla açar. Aksi halde giriş sınıfı parent'tan
 * çözülür ve registry INVALID_ARCHIVE verir.
 */
public final class Harness {

    private static final long CALL_TIMEOUT_SECONDS = 90L;

    public static void main(String[] args) {
        if (args.length < 2 && System.getenv("HARNESS_DUMP") == null) {
            System.err.println("kullanım: Harness <extension.jar> <domain> [domain...]");
            System.exit(2);
        }

        String jarArg = args[0];
        List<String> domains = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            String d = args[i].trim().toLowerCase(Locale.ROOT).replaceFirst("^www\\.", "");
            if (!d.isEmpty()) {
                domains.add(d);
            }
        }

        MihonDesktopPlatform platform = null;
        MihonJarRegistry registry = null;
        FileSourcePreferenceStore preferences = null;
        try {
            // Paralel koşu: her süreç kendi kök dizinini kullanır (HARNESS_ROOT),
            // aksi hâlde iki JVM aynı `.work/harness-tmp/preferences` kilidine
            // takılıp "Preference directory already has an owner" veriyor.
            String rootOverride = System.getenv("HARNESS_ROOT");
            Path root = (rootOverride == null || rootOverride.isBlank())
                    ? Paths.get("").toAbsolutePath()
                    : Paths.get(rootOverride).toAbsolutePath();
            Path work = root.resolve(".work").resolve("harness-tmp");
            Path compat = work.resolve("compat");
            Path prefsDir = work.resolve("preferences");
            Path catalog = work.resolve("catalog");
            Files.createDirectories(compat);
            Files.createDirectories(prefsDir);
            Files.createDirectories(catalog);

            Path jar = Paths.get(jarArg).toAbsolutePath().normalize();
            if (!Files.isRegularFile(jar)) {
                throw new IllegalStateException("jar yok: " + jar);
            }

            // 1) Kototoro masaüstü platformu: Injekt/Koin bağlamını kurar;
            //    eklentinin `Injekt.get<Application>()` çağrısı ancak bundan
            //    sonra gerçek bir Application döndürür.
            preferences = new FileSourcePreferenceStore(prefsDir, 8 * 1024 * 1024);
            platform = new MihonDesktopPlatform(compat, null, false, null, null);
            ClassLoader compatibilityLoader = platform.initialize(preferences);
            if (compatibilityLoader == null) {
                compatibilityLoader = Thread.currentThread().getContextClassLoader();
            }

            // 2) JAR kimliği ve kaydı.
            MihonJarInspector inspector = new MihonJarInspector();
            MihonJarMetadata metadata = inspector.inspect(jar);
            MihonJarIdentity identity = new MihonJarIdentity(
                    metadata.getPackageName(), metadata.getVersionCode(), metadata.getSha256());
            registry = new MihonJarRegistry(compatibilityLoader, inspector, catalog);
            LoadedMihonExtension extension = registry.load(jar, identity);

            List<MihonSourceDescriptor> descriptors = extension.getSources();
            System.out.println("# KAYNAK_SAYISI " + descriptors.size());

            Object anchor = null;
            if (!descriptors.isEmpty()) {
                kotlin.jvm.functions.Function1<Object, Object> anchorIdentity = value -> value;
                try {
                    anchor = registry.withSource$Kototoro_source_host(
                            descriptors.get(0).getSource().getName(), anchorIdentity);
                } catch (Throwable ignored) {
                    // aşağıdaki onarım yolu yine de denenir
                }
            }

            List<Object> instances = repairedSources(jar, anchor, descriptors, registry);
            System.out.println("# KAYNAK_SAYISI_ONARIM " + instances.size());

            Map<String, JSONObject> catalogue = loadCatalogue(jar);
            System.out.println("# KATALOG_SAYISI " + catalogue.size());

            // Paket allowlist'i (PulsarData allowed) yayınlanmamış katalog
            // kaynaklarını eler; hiçbir pakette bulunmayanlar bu yüzden
            // KAPSAM_DISI kalıyordu. HARNESS_KATALOG=1 ile eksik katalog
            // kaynakları doğrudan PulsarSource olarak örneklenir.
            instances = addCatalogueOnlySources(instances, catalogue);
            System.out.println("# KAYNAK_SAYISI_KATALOG " + instances.size());

            if (System.getenv("HARNESS_DUMP") != null) {
                dumpSources(instances, catalogue);
            }

            for (String domain : domains) {
                System.out.println(runDomain(instances, domain, catalogue.get(domain)));
            }
        } catch (Throwable t) {
            // Hata olsa bile her domain için satır yaz.
            String error = shortError(t);
            for (String domain : domains) {
                System.out.println(errorLine(domain, 0, 0, 0, error, ""));
            }
            System.err.println("HARNESS_FATAL " + error);
        } finally {
            if (registry != null) {
                try {
                    registry.close();
                } catch (Throwable ignored) {
                    // kapanış hatası sonucu değiştirmez
                }
            }
            if (platform != null) {
                try {
                    platform.close();
                } catch (Throwable ignored) {
                    // kapanış hatası sonucu değiştirmez
                }
            }
            if (preferences != null) {
                try {
                    preferences.close();
                } catch (Throwable ignored) {
                    // kapanış hatası sonucu değiştirmez
                }
            }
        }
    }

    private static String runDomain(List<Object> instances, String domain, JSONObject entry) {
        try {
            Object instance = findSource(instances, domain, entry);
            if (instance == null) {
                // Katalogda olup 288'lik çalıştırılabilir listede kaynağı olmayan
                // domainler site hatası değil, kapsam dışıdır.
                String reason = entry != null ? "KAPSAM_DISI" : "KATALOG_DISI";
                return errorLine(domain, 0, 0, 0, reason, "");
            }
            if (!(instance instanceof CatalogueSource)) {
                return errorLine(domain, 0, 0, 0,
                        "kaynak CatalogueSource değil: " + instance.getClass().getName(), "");
            }
            CatalogueSource source = (CatalogueSource) instance;

            MangasPage page = source.fetchPopularManga(1)
                    .timeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                    .toBlocking().first();
            List<SManga> manga = page != null ? page.getMangas() : new ArrayList<>();
            int listCount = manga.size();
            if (listCount == 0) {
                return errorLine(domain, 0, 0, 0, "popüler liste boş", "");
            }

            // İlk kart her sitede dolu değil (ör. okutoon'da Personant 0 bölümlü,
            // Absolute Domination 234 bölümlü). Bölüm ölçümü için listedeki ilk
            // 6 seriyi sırayla dene; ilk bölümlü seride dur.
            int maxSeries = Math.min(6, listCount);
            int attemptedSeries = 0;
            SManga sampled = null;
            List<SChapter> chapters = null;
            int chapterCount = 0;
            for (int i = 0; i < maxSeries; i++) {
                SManga candidate = manga.get(i);
                attemptedSeries++;
                try {
                    SManga details = source.fetchMangaDetails(candidate)
                            .timeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                            .toBlocking().first();
                    if (details == null) {
                        details = candidate;
                    }
                    List<SChapter> candidateChapters = source.fetchChapterList(details)
                            .timeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                            .toBlocking().first();
                    int candidateCount = candidateChapters != null ? candidateChapters.size() : 0;
                    if (candidateCount > 0) {
                        sampled = candidate;
                        chapters = candidateChapters;
                        chapterCount = candidateCount;
                        break;
                    }
                } catch (Throwable t) {
                    System.err.println("HARNESS_SERI_ATLANDI " + domain + " #" + i
                            + " " + shortError(t));
                }
            }

            String sample = sampled != null
                    ? (sampled.getTitle() != null ? sampled.getTitle() : "")
                    : attemptedSeries + " seri denendi";
            if (chapterCount == 0) {
                return errorLine(domain, listCount, 0, 0, "bölüm listesi boş", sample);
            }

            // Sayfa ölçümü için ilk, orta ve son bölüm (en fazla 3).
            int[] probeIndexes = {0, chapterCount / 2, chapterCount - 1};
            int pageCount = 0;
            int probed = 0;
            for (int i = 0; i < probeIndexes.length && probed < 3; i++) {
                int index = probeIndexes[i];
                boolean duplicate = false;
                for (int j = 0; j < i; j++) {
                    if (probeIndexes[j] == index) {
                        duplicate = true;
                        break;
                    }
                }
                if (duplicate) {
                    continue;
                }
                probed++;
                try {
                    List<Page> pages = source.fetchPageList(chapters.get(index))
                            .timeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                            .toBlocking().first();
                    pageCount = pages != null ? pages.size() : 0;
                    // Sahte geçiş koruması: sayfa listesi HTML belgesi döndürüyorsa
                    // okuyucuda kırık görsel olur. Yalnız kesin text/html reddedilir;
                    // ağ hatasında sayı korunur (yanlış negatif üretmemek için).
                    // DİKKAT: Page.url bölüm adresidir; görsel adresi imageUrl'dedir.
                    if (pageCount > 0) {
                        String img = pages.get(0).getImageUrl();
                        if (img == null || img.isEmpty()) img = pages.get(0).getUrl();
                        if (isHtmlPage(img)) {
                            System.err.println("HARNESS_SAYFA_HTML " + domain + " #" + index + " " + img);
                            pageCount = 0;
                        }
                    }
                } catch (Throwable t) {
                    System.err.println("HARNESS_SAYFA_ATLANDI " + domain + " #" + index
                            + " " + shortError(t));
                    pageCount = 0;
                }
                if (pageCount > 0) {
                    break;
                }
            }

            return jsonLine(domain, listCount, chapterCount, pageCount, "", sample);
        } catch (Throwable t) {
            return errorLine(domain, 0, 0, 0, shortError(t), "");
        }
    }

    /**
     * Kaynak örneğini domain ile eşleştirir.
     *
     * Sıra: (a) kaynağın katalog `domain` alanı, (b) katalog domain/lang'inden
     * hesaplanan `pulsar/...` id'si, (c) baseUrl host'u (alt domainler dahil),
     * (d) katalog adı. 288'lik listede `PulsarSource` (katalog kaynaklı) ve
     * `PulsarKotatsuSource` (Kotatsu parser kaynaklı) karışık gelir; id/host
     * eşleşmesi ikisini de yakalar.
     */
    private static Object findSource(List<Object> instances, String domain, JSONObject entry) {
        String lang = entry != null
                ? entry.optString("lang", "tr").toLowerCase(Locale.ROOT)
                : "tr";
        String expectedName = entry != null ? normalizeName(entry.optString("name", "")) : "";
        long expectedId = pulsarId(domain, lang);

        Set<String> hosts = new HashSet<>();
        hosts.add(hostOfUrl(domain));
        if (entry != null) {
            addHosts(hosts, entry.optJSONArray("altDomains"));
            addHosts(hosts, entry.optJSONArray("mirrors"));
        }

        // Katalog kaynağı (PulsarSource) motor kaynağından (PulsarKotatsuSource) ÖNCE
        // denenir. Aksi hâlde aynı host'u taşıyan @Broken motor kaynağı eşleşip
        // UnsupportedOperationException veriyor ve çalışan katalog kaydı hiç test
        // edilmiyordu (§30'daki aynı tuzak). Motor kaynakları yine de yedek sırada.
        List<Object> ordered = new ArrayList<>();
        for (Object candidate : instances) {
            if (isCatalogueSource(candidate)) ordered.add(candidate);
        }
        for (Object candidate : instances) {
            if (!isCatalogueSource(candidate)) ordered.add(candidate);
        }

        // (a) katalog domain alanı
        for (Object candidate : ordered) {
            String candidateDomain = domainOf(candidate);
            if (candidateDomain != null) {
                String candidateHost = hostOfUrl(candidateDomain.toLowerCase(Locale.ROOT));
                if (candidateHost != null && candidateHost.equals(domain)) {
                    return candidate;
                }
            }
        }

        // (b) id
        for (Object candidate : ordered) {
            if (idOf(candidate) == expectedId) {
                return candidate;
            }
        }

        // (c) baseUrl host
        for (Object candidate : ordered) {
            String host = hostOfUrl(baseUrlOf(candidate));
            if (host != null && hosts.contains(host)) {
                return candidate;
            }
        }

        // (d) ad
        for (Object candidate : ordered) {
            String candidateName = normalizeName(nameOf(candidate));
            if (!candidateName.isEmpty() && candidateName.equals(expectedName)) {
                return candidate;
            }
        }
        return null;
    }

    private static List<Object> addCatalogueOnlySources(List<Object> instances,
                                                        Map<String, JSONObject> catalogue) {
        if (System.getenv("HARNESS_KATALOG") == null) {
            return instances;
        }
        Class<?> sourceClass = null;
        for (Object source : instances) {
            if ("PulsarSource".equals(source.getClass().getSimpleName())) {
                sourceClass = source.getClass();
                break;
            }
        }
        if (sourceClass == null) {
            System.err.println("HARNESS_KATALOG_ERR PulsarSource sınıfı yok");
            return instances;
        }
        java.lang.reflect.Constructor<?> ctor = null;
        for (java.lang.reflect.Constructor<?> candidate : sourceClass.getDeclaredConstructors()) {
            Class<?>[] params = candidate.getParameterTypes();
            if (params.length == 2 && "org.json.JSONObject".equals(params[0].getName())
                    && params[1] == String.class) {
                ctor = candidate;
                break;
            }
        }
        if (ctor == null) {
            System.err.println("HARNESS_KATALOG_ERR (JSONObject,String) kurucusu yok");
            return instances;
        }
        ctor.setAccessible(true);
        Set<Long> ids = new HashSet<>();
        for (Object source : instances) {
            ids.add(idOf(source));
        }
        int added = 0;
        for (JSONObject entry : catalogue.values()) {
            String domain = entry.optString("domain", "")
                    .toLowerCase(Locale.ROOT).replaceFirst("^www\\.", "");
            String lang = entry.optString("lang", "all");
            if (domain.isEmpty()) {
                continue;
            }
            long id = pulsarId(domain, lang);
            if (ids.contains(id)) {
                continue;
            }
            try {
                Object payload = entry;
                if (!ctor.getParameterTypes()[0].isInstance(payload)) {
                    payload = ctor.getParameterTypes()[0]
                            .getConstructor(String.class).newInstance(entry.toString());
                }
                instances.add(ctor.newInstance(payload, lang));
                ids.add(id);
                added++;
            } catch (Throwable t) {
                System.err.println("HARNESS_KATALOG_EKLE " + domain + " " + shortError(t));
            }
        }
        System.out.println("# KATALOG_EKLENEN " + added);
        return instances;
    }

    private static Map<String, JSONObject> loadCatalogue(Path jar) {
        Map<String, JSONObject> result = new HashMap<>();
        try {
            String text = readZipEntry(jar, "assets/catalogue.json");
            JSONArray sources = new JSONObject(text).optJSONArray("sources");
            if (sources != null) {
                for (int i = 0; i < sources.length(); i++) {
                    JSONObject entry = sources.optJSONObject(i);
                    if (entry == null) {
                        continue;
                    }
                    String domain = hostOfUrl(entry.optString("domain", "").toLowerCase(Locale.ROOT));
                    if (domain != null && !domain.isEmpty()) {
                        result.put(domain, entry);
                    }
                }
            }
        } catch (Throwable t) {
            System.err.println("HARNESS_CATALOGUE_ERR " + shortError(t));
        }
        return result;
    }

    private static void dumpSources(List<Object> instances, Map<String, JSONObject> catalogue) {
        int index = 0;
        for (Object source : instances) {
            System.out.println("# KAYNAK " + (index++)
                    + " sinif=" + source.getClass().getSimpleName()
                    + " id=" + idOf(source)
                    + " ad=" + nameOf(source)
                    + " domain=" + domainOf(source)
                    + " baseUrl=" + baseUrlOf(source));
        }
        System.out.println("# KATALOG_DOMAIN " + catalogue.size());
    }

    private static void addHosts(Set<String> hosts, JSONArray values) {
        if (values == null) {
            return;
        }
        for (int i = 0; i < values.length(); i++) {
            String host = hostOfUrl(values.optString(i, ""));
            if (host != null && !host.isEmpty()) {
                hosts.add(host);
            }
        }
    }

    private static String hostOfUrl(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        try {
            String host = URI.create(value.contains("://") ? value : "https://" + value).getHost();
            return host == null ? null : host.toLowerCase(Locale.ROOT).replaceFirst("^www\\.", "");
        } catch (Throwable t) {
            return null;
        }
    }

    private static String domainOf(Object source) {
        try {
            Object value = source.getClass().getMethod("getDomain").invoke(source);
            return value instanceof String ? (String) value : null;
        } catch (Throwable t) {
            return null;
        }
    }

    private static long idOf(Object source) {
        try {
            Object value = source.getClass().getMethod("getId").invoke(source);
            return value instanceof Number ? ((Number) value).longValue() : 0L;
        } catch (Throwable t) {
            return 0L;
        }
    }

    private static String nameOf(Object source) {
        try {
            Object value = source.getClass().getMethod("getName").invoke(source);
            return value instanceof String ? (String) value : "";
        } catch (Throwable t) {
            return "";
        }
    }

    private static String normalizeName(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char c = Character.toLowerCase(value.charAt(i));
            if (Character.isLetterOrDigit(c)) {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    /** PulsarSource.getId() ile aynı hash: "pulsar/<domain>/<lang>". */
    private static long pulsarId(String domain, String lang) {
        String key = "pulsar/" + domain + "/" + lang;
        long hash = 1125899906842597L;
        for (int i = 0; i < key.length(); i++) {
            hash = 31L * hash + key.charAt(i);
        }
        return hash & 0x7fffffffffffffffL;
    }

    /**
     * Kaynak listesini üretir.
     *
     * APK'nın gömülü `CATALOGUE_B64` değeri bozuk (uzunluk %4==1; Android
     * Base64 "wrong 4-byte ending unit" veriyor), bu yüzden ilk
     * `createSources()` katalog katmanını boş görüyor. JAR'ın içindeki
     * sağlam `assets/catalogue.json`ı PulsarData'nın lazy alanına geri
     * bağlayıp aynı sınıf yükleyicide fabrikayı yeniden çalıştırıyoruz.
     * Bu, yalnızca bozuk gömülü kopyayı APK'nın kendi asset'iyle onarır;
     * kaynak kodu veya filtre değişmez.
     */
    private static List<Object> repairedSources(Path jar, Object anchor,
                                                List<MihonSourceDescriptor> descriptors,
                                                MihonJarRegistry registry) {
        List<Object> result = new ArrayList<>();
        try {
            if (anchor == null) {
                throw new IllegalStateException("eklenti sınıf yükleyicisi alınamadı");
            }
            String catalogue = readZipEntry(jar, "assets/catalogue.json");
            ClassLoader loader = anchor.getClass().getClassLoader();
            Class<?> dataClass = Class.forName("eu.kanade.tachiyomi.extension.all.pulsar.PulsarData", true, loader);
            Object data = dataClass.getField("INSTANCE").get(null);

            // Bozuk gömülü veriyi raporla (sayı uydurulmaz, gerçek uzunluk).
            java.lang.reflect.Field b64Field = dataClass.getDeclaredField("CATALOGUE_B64");
            b64Field.setAccessible(true);
            String rawB64 = (String) b64Field.get(data);
            System.err.println("HARNESS_PROBE gomulu_b64_len=" + rawB64.length()
                    + " mod4=" + (rawB64.length() % 4)
                    + " asset_catalogue_len=" + catalogue.length()
                    + " asset_domain_sayisi=" + countOf(catalogue, "\"domain\":"));

            kotlin.Lazy<String> fixed = new kotlin.Lazy<String>() {
                @Override
                public String getValue() {
                    return catalogue;
                }

                @Override
                public boolean isInitialized() {
                    return true;
                }
            };
            setStaticFinal(dataClass, "catalogue$delegate", fixed);
            setStaticFinal(dataClass, "CATALOGUE_B64",
                    java.util.Base64.getEncoder().encodeToString(
                            catalogue.getBytes(java.nio.charset.StandardCharsets.UTF_8)));

            Class<?> factoryClass = Class.forName(
                    "eu.kanade.tachiyomi.extension.all.pulsar.PulsarSourceFactory", true, loader);
            Object factory = factoryClass.getDeclaredConstructor().newInstance();
            Object sources = factoryClass.getMethod("createSources").invoke(factory);
            if (sources instanceof List) {
                result.addAll((List<?>) sources);
            }
            System.err.println("HARNESS_REPAIR onarimli_kaynak_sayisi=" + result.size());
        } catch (Throwable t) {
            System.err.println("HARNESS_REPAIR_ERR " + shortError(t));
        }

        if (result.isEmpty()) {
            // Onarım çalışmazsa registry'nin ürettiği kaynaklarla devam et.
            for (MihonSourceDescriptor descriptor : descriptors) {
                try {
                    kotlin.jvm.functions.Function1<Object, Object> identity = value -> value;
                    result.add(registry.withSource$Kototoro_source_host(
                            descriptor.getSource().getName(), identity));
                } catch (Throwable ignored) {
                    // bu kaynak atlanır
                }
            }
        }
        return result;
    }

    private static String readZipEntry(Path jar, String entry) throws Exception {
        try (java.util.zip.ZipFile zip = new java.util.zip.ZipFile(jar.toFile())) {
            java.util.zip.ZipEntry e = zip.getEntry(entry);
            if (e == null) {
                throw new IllegalStateException("JAR içinde yok: " + entry);
            }
            try (java.io.InputStream in = zip.getInputStream(e)) {
                return new String(in.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            }
        }
    }

    /** Java 21'de static final alanı Unsafe ile değiştirir (harness'a özel). */
    private static void setStaticFinal(Class<?> owner, String name, Object value) throws Exception {
        java.lang.reflect.Field field = owner.getDeclaredField(name);
        field.setAccessible(true);
        Class<?> unsafeClass = Class.forName("sun.misc.Unsafe");
        java.lang.reflect.Field unsafeField = unsafeClass.getDeclaredField("theUnsafe");
        unsafeField.setAccessible(true);
        Object unsafe = unsafeField.get(null);
        Method base = unsafeClass.getMethod("staticFieldBase", java.lang.reflect.Field.class);
        Method offset = unsafeClass.getMethod("staticFieldOffset", java.lang.reflect.Field.class);
        Method put = unsafeClass.getMethod("putObject", Object.class, long.class, Object.class);
        put.invoke(unsafe, base.invoke(unsafe, field), offset.invoke(unsafe, field), value);
    }

    private static String sourceNameOf(Object source) {
        try {
            return String.valueOf(source.getClass().getMethod("getName").invoke(source));
        } catch (Throwable t) {
            return source.getClass().getSimpleName();
        }
    }

    private static int countOf(String text, String needle) {
        int count = 0;
        int index = 0;
        while ((index = text.indexOf(needle, index)) >= 0) {
            count++;
            index += needle.length();
        }
        return count;
    }

    private static String baseUrlOf(Object source) {
        try {
            Method m = source.getClass().getMethod("getBaseUrl");
            Object value = m.invoke(source);
            return value instanceof String ? (String) value : null;
        } catch (Throwable t) {
            // HttpSource alt sınıfı değilse alan adı yoktur.
            System.err.println("HARNESS_BASEURL_ERR " + source.getClass().getName() + " | " + shortError(t));
            return null;
        }
    }

    /** Katalog (veri-güdümlü) kaynağı mı? Motor kaynağı `PulsarKotatsuSource`'tur. */
    private static boolean isCatalogueSource(Object candidate) {
        return candidate != null && candidate.getClass().getSimpleName().equals("PulsarSource");
    }

    /**
     * Sayfa adresi gerçekten görsel mi? Yalnız kesin `text/html` reddedilir.
     *
     * Neden: sayfa listesi HTML belgesi döndüren kaynaklar (ör. `/view/12/3/`
     * okuyucu sayfası) harness'ta `pages=201` gibi "geçti" görünüyor, oysa
     * uygulamada her biri kırık görsel olur. Ağ hatasında true döneriz: yanlış
     * negatif üretip çalışan kaynağı düşürmek daha kötü.
     */
    private static boolean isHtmlPage(String url) {
        if (url == null || !url.startsWith("http")) return false;
        java.net.HttpURLConnection c = null;
        try {
            c = (java.net.HttpURLConnection) URI.create(url).toURL().openConnection();
            c.setRequestMethod("HEAD");
            c.setInstanceFollowRedirects(true);
            c.setConnectTimeout(8000);
            c.setReadTimeout(8000);
            c.setRequestProperty("User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36");
            int code = c.getResponseCode();
            // Yalnız 200 + text/html KESİN reddedilir. 401/403/405/5xx belirsizdir:
            // hotlink koruması (2xstorage: referersiz 403 text/html, refererli 200 webp)
            // ve oturum çerezi isteyen uçlar aksi hâlde çalışan kaynağı düşürür.
            if (code != 200 && code != 206) {
                return false;
            }
            String ct = c.getContentType();
            return ct != null && ct.toLowerCase(Locale.ROOT).contains("text/html");
        } catch (Throwable t) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static String jsonLine(String domain, int list, int chapters, int pages, String error, String sample) {
        return "{\"domain\":\"" + escape(domain) + "\",\"list\":" + list
                + ",\"chapters\":" + chapters + ",\"pages\":" + pages
                + ",\"hata\":\"" + escape(error) + "\",\"ornek\":\"" + escape(sample) + "\"}";
    }

    private static String errorLine(String domain, int list, int chapters, int pages, String error, String sample) {
        return jsonLine(domain, list, chapters, pages, error, sample);
    }

    private static String escape(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(value.length() + 8);
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\':
                    sb.append("\\\\");
                    break;
                case '"':
                    sb.append("\\\"");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }

    private static String shortError(Throwable t) {
        Throwable root = t;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }
        String message = root.getClass().getSimpleName()
                + (root.getMessage() != null ? ": " + root.getMessage() : "");
        // Satır sonları " | " olur: RxJava sarmalayıcısında iç istisna metni
        // ilk satırdan sonra gelir, boşlukla birleştirilince kayboluyordu.
        message = message.replace("\r\n", " | ")
                .replace("\n", " | ")
                .replace("\r", " | ")
                .trim();
        if (message.length() > 500) {
            message = message.substring(0, 500);
        }
        String rootName = root.getClass().getName();
        if (rootName.contains("OnNextValue") || rootName.endsWith("OnErrorThrowable")) {
            StringBuilder chain = new StringBuilder();
            Set<Throwable> seen = java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<Throwable, Boolean>());
            Throwable current = t;
            while (current != null && seen.add(current)) {
                if (chain.length() > 0) {
                    chain.append(" <- ");
                }
                chain.append(current.getClass().getName());
                if (current == root) {
                    break;
                }
                current = current.getCause();
            }
            message = message + " [zincir: " + chain + "]";
        }
        return message;
    }

    private Harness() {
    }
}
