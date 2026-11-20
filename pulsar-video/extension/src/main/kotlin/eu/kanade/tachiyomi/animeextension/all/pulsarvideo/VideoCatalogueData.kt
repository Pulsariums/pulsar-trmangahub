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
    {"id":"animepahe.com","name":"AnimePahe","lang":"en","nsfw":0,"domain":"animepahe.com","baseUrl":"https://animepahe.com","engine":"video","config":{}},
    {"id":"allanime.day","name":"AllAnime","lang":"en","nsfw":0,"domain":"allanime.day","baseUrl":"https://allanime.day","engine":"video","config":{}}
  ]
}
"""
