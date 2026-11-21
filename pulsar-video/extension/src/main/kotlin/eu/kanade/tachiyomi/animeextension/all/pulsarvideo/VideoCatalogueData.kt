package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

/**
 * Gömülü video kataloğu. `pulsar-video/data/video-catalogue.json` ile aynı içerik.
 * ÜRETİLEN VERİ: ileride `pulsar embed-video` (Rust) bu sabiti JSON'dan üretecek;
 * şimdilik elle senkron tutulur. Config'i boş kaynaklar fabrikada oluşturulmaz.
 */
internal const val VIDEO_CATALOGUE: String = """
{
  "sources": [
    {"id":"9anime.org.lv","name":"9Anime","lang":"en","nsfw":0,"domain":"9anime.org.lv","baseUrl":"https://9anime.org.lv","engine":"video","config":{}},
    {"id":"gogoanime3.net","name":"GogoAnime","lang":"en","nsfw":0,"domain":"gogoanime3.net","baseUrl":"https://gogoanime3.net","engine":"video","config":{}},
    {"id":"gogoanime.onl","name":"GogoAnime","lang":"en","nsfw":0,"domain":"gogoanime.onl","baseUrl":"https://gogoanime.onl","engine":"video","status":"measured","config":{"listPath":"/anime","itemSelector":"ul#anime-list-items li","titleAttr":"title","episodeSelector":"ul#episode_related li a","hosterSelector":"div.anime_muti_link ul li a","hosterUrlAttr":"data-video","hosterUrlBase64":"1","userAgent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},"not":"2026-11-21: liste/detay/bolum olculdu; vidmoly embed -> master.m3u8 200 mpegurl. Liste ul#anime-list-items li (div.img=0, gorsel yok -> coverSelector yok); hoster linkleri div.anime_muti_link ul li a[href='#'][data-video] base64."},
    {"id":"animepahe.com","name":"AnimePahe","lang":"en","nsfw":0,"domain":"animepahe.com","baseUrl":"https://animepahe.com","engine":"video","config":{}},
    {"id":"allanime.day","name":"AllAnime","lang":"en","nsfw":0,"domain":"allanime.day","baseUrl":"https://allanime.day","engine":"video","config":{}}
  ]
}
"""
