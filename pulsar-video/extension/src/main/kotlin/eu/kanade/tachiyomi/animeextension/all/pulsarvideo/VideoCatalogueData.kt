package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

/**
 * Gömülü video kataloğu. `pulsar-video/data/video-catalogue.json` ile aynı içerik.
 * ÜRETİLEN VERİ: ileride `pulsar embed-video` (Rust) bu sabiti JSON'dan üretecek;
 * şimdilik elle senkron tutulur. Config'i boş kaynaklar fabrikada oluşturulmaz.
 */
internal const val VIDEO_CATALOGUE: String = """
{
  "sources": [
    {"id":"gogoanime.onl","name":"GogoAnime","lang":"en","nsfw":0,"domain":"gogoanime.onl","baseUrl":"https://gogoanime.onl","engine":"video","status":"measured","config":{"listPath":"/anime","itemSelector":"ul#anime-list-items li","titleAttr":"title","episodeSelector":"ul#episode_related li a","hosterSelector":"div.anime_muti_link ul li a","hosterUrlAttr":"data-video","hosterUrlBase64":"1","userAgent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},"not":"2026-11-21: liste/detay/bolum olculdu; vidmoly embed -> master.m3u8 200 mpegurl. Liste ul#anime-list-items li (div.img=0, gorsel yok -> coverSelector yok); hoster linkleri div.anime_muti_link ul li a[href='#'][data-video] base64."},
    {"id":"animepahe.com","name":"AnimePahe","lang":"en","nsfw":0,"domain":"animepahe.com","baseUrl":"https://animepahe.com","engine":"video","status":"unmeasured","config":{},"not":"301 -> yonlendirme; hedef olculmedi."},
    {"id":"allanime.day","name":"AllAnime","lang":"en","nsfw":0,"domain":"allanime.day","baseUrl":"https://allanime.day","engine":"video","status":"unmeasured","config":{},"not":"OLU HOST: kok adres kendine 301 dongusu kuruyor, www nginx varsayilan sayfasi donuyor. Icerik allmanga.to'ya tasinmis; allmanga.to Nuxt SPA, HTML'de kart/anime linki 0. GraphQL POST gerektiginden config yazilamadi."}
  ]
}
"""
