class SentimentAnalyzer:
    def __init__(self):
        self.positive_keywords = ['growth', 'bull', 'buy', 'high', 'profit']
        self.negative_keywords = ['drop', 'bear', 'sell', 'low', 'loss']

    def analyze(self, text_list):
        if not text_list: return 0.0
        score = 0
        for text in text_list:
            t = text.lower()
            for w in self.positive_keywords: 
                if w in t: score += 1
            for w in self.negative_keywords: 
                if w in t: score -= 1
        return score / len(text_list)