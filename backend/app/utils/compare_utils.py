import re
import json
import math
from difflib import SequenceMatcher

try:
    from Levenshtein import ratio as levenshtein_ratio
except ImportError:
    def levenshtein_ratio(str1, str2):
        return SequenceMatcher(None, str1, str2).ratio()

def preprocess_text(text):
    text = re.sub(r'[^\w\s。；！？\.\;\!\?]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def split_sentences(text):
    pattern = r'([。；！？\.\;\!\?])'
    parts = re.split(pattern, text)
    sentences = []
    for i in range(0, len(parts)-1, 2):
        sentence = parts[i] + parts[i+1]
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence)
    return sentences

def tokenize(text):
    import jieba
    words = jieba.lcut(text)
    return [w for w in words if len(w) > 1]

def compute_tfidf(documents):
    doc_tokens = [tokenize(doc) for doc in documents]
    all_words = list(set(word for tokens in doc_tokens for word in tokens))
    
    word_to_id = {word: i for i, word in enumerate(all_words)}
    idf = {}
    num_docs = len(documents)
    
    for word in all_words:
        doc_count = sum(1 for tokens in doc_tokens if word in tokens)
        idf[word] = math.log(num_docs / (1 + doc_count)) if num_docs > 0 else 0.0
    
    tfidf_vectors = []
    for tokens in doc_tokens:
        tf = {}
        for word in tokens:
            tf[word] = tf.get(word, 0) + 1
        max_tf = max(tf.values()) if tf else 1
        
        vector = [0.0] * len(all_words)
        for word, count in tf.items():
            if word in word_to_id:
                vector[word_to_id[word]] = (count / max_tf) * idf[word]
        tfidf_vectors.append(vector)
    
    return tfidf_vectors

def dot_product(vec1, vec2):
    return sum(a * b for a, b in zip(vec1, vec2))

def vector_norm(vec):
    return math.sqrt(sum(x * x for x in vec))

def cosine_similarity(vec1, vec2):
    dot = dot_product(vec1, vec2)
    norm1 = vector_norm(vec1)
    norm2 = vector_norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def calculate_similarity(str1, str2):
    lev_sim = levenshtein_ratio(str1, str2)
    
    try:
        vectors = compute_tfidf([str1, str2])
        cos_sim = cosine_similarity(vectors[0], vectors[1])
    except:
        cos_sim = 0.0
    
    return lev_sim, cos_sim

def weighted_similarity(str1, str2, alpha=0.6, beta=0.4):
    levenshtein_ratio_val, cosine_sim = calculate_similarity(str1, str2)
    return alpha * levenshtein_ratio_val + beta * cosine_sim

def classify_similarity(similarity):
    if similarity >= 1.0:
        return "100%"
    elif similarity >= 0.8:
        return "80-99%"
    elif similarity >= 0.7:
        return "70-80%"
    else:
        return "<70%"

def determine_verdict(similarity):
    if similarity >= 0.8:
        return "pass"
    elif similarity >= 0.6:
        return "review"
    else:
        return "force_review"

def classify_diff_type(text_a, text_b):
    if not text_a and text_b:
        return "add"
    elif text_a and not text_b:
        return "delete"
    else:
        return "modify"

def compare_documents(text_a, text_b, config=None):
    if config is None:
        config = {"threshold": 0.8, "alpha": 0.6, "beta": 0.4}
    
    text_a = preprocess_text(text_a)
    text_b = preprocess_text(text_b)
    
    sentences_a = split_sentences(text_a)
    sentences_b = split_sentences(text_b)
    
    matched_b = set()
    diffs = []
    
    for i, sent_a in enumerate(sentences_a):
        best_match = None
        best_sim = 0.0
        best_j = -1
        
        for j, sent_b in enumerate(sentences_b):
            if j in matched_b:
                continue
            
            sim = weighted_similarity(sent_a, sent_b, config["alpha"], config["beta"])
            
            if sim > best_sim:
                best_sim = sim
                best_match = sent_b
                best_j = j
        
        if best_match is not None:
            if best_sim < config["threshold"]:
                diffs.append({
                    "diff_type": classify_diff_type(sent_a, best_match),
                    "severity": "high" if best_sim < 0.7 else "medium",
                    "similarity": best_sim,
                    "text_a": sent_a,
                    "text_b": best_match,
                    "position_a": {"sentence": i},
                    "position_b": {"sentence": best_j},
                    "chapter": ""
                })
            matched_b.add(best_j)
    
    for j, sent_b in enumerate(sentences_b):
        if j not in matched_b:
            diffs.append({
                "diff_type": "add",
                "severity": "high",
                "similarity": 0.0,
                "text_a": "",
                "text_b": sent_b,
                "position_a": {},
                "position_b": {"sentence": j},
                "chapter": ""
            })
    
    overall_similarity = 1.0
    if sentences_a or sentences_b:
        total = len(sentences_a) + len(sentences_b)
        matched = len([d for d in diffs if d["similarity"] >= config["threshold"]]) + \
                  (len(sentences_a) + len(sentences_b) - len(diffs))
        overall_similarity = matched / total if total > 0 else 1.0
    
    diff_stats = {
        "add": len([d for d in diffs if d["diff_type"] == "add"]),
        "delete": len([d for d in diffs if d["diff_type"] == "delete"]),
        "modify": len([d for d in diffs if d["diff_type"] == "modify"])
    }
    
    verdict = determine_verdict(overall_similarity)
    
    return {
        "similarity": overall_similarity,
        "verdict": verdict,
        "total_diffs": len(diffs),
        "diff_stats": diff_stats,
        "diffs": diffs
    }
