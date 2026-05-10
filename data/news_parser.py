import feedparser
def fetch_financial_news():
    url = "https://rssexport.rbc.ru/rbcnews/export/rss/rbcnews_science.xml"
    try:
        feed = feedparser.parse(url)
        return " ".join([e.title for e in feed.entries[:3]])
    except:
        return "Новостей нет"