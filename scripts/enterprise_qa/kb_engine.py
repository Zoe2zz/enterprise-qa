import os
import re
import math
from collections import Counter, defaultdict


def _tokenize(text: str) -> list[str]:
    try:
        import jieba
        words = jieba.lcut(text.lower())
        return [w for w in words if w.strip() and len(w.strip()) > 0]
    except ImportError:
        text = text.lower()
        tokens = []
        for i in range(len(text) - 2):
            ch = text[i:i+3]
            if ch.strip():
                tokens.append(ch)
        return tokens


class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus: list[dict] = []
        self.doc_count = 0
        self.avg_doc_length = 0.0
        self.doc_lengths: list[int] = []
        self.idf: dict[str, float] = {}
        self.all_tokens: list[list[str]] = []

    def add_document(self, text: str, metadata: dict):
        self.corpus.append({"text": text, "metadata": metadata})

    def build_index(self):
        self.doc_count = len(self.corpus)
        if self.doc_count == 0:
            return

        self.doc_lengths = []
        self.all_tokens = []

        for doc in self.corpus:
            tokens = _tokenize(doc["text"])
            self.all_tokens.append(tokens)
            self.doc_lengths.append(len(tokens))

        self.avg_doc_length = sum(self.doc_lengths) / self.doc_count

        df: dict[str, int] = defaultdict(int)
        for tokens in self.all_tokens:
            for token in set(tokens):
                df[token] += 1

        self.idf = {
            token: math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1)
            for token, freq in df.items()
        }

    def search(self, query: str, top_k: int = 3) -> list[tuple[int, float]]:
        query_tokens = _tokenize(query)
        if not query_tokens or self.doc_count == 0:
            return []

        scores: list[tuple[int, float]] = []
        for i in range(self.doc_count):
            score = 0.0
            doc_term_counts = Counter(self.all_tokens[i])
            for token in query_tokens:
                if token in self.idf:
                    tf = doc_term_counts.get(token, 0)
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (
                        1 - self.b + self.b * self.doc_lengths[i] / self.avg_doc_length
                    )
                    if denominator > 0:
                        score += self.idf[token] * numerator / denominator
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in scores if s > 0][:top_k]


class KBEngine:
    def __init__(self, kb_path: str):
        self.kb_path = kb_path
        self.retriever = BM25()
        self._load_and_index()

    def _load_and_index(self):
        if not os.path.exists(self.kb_path):
            raise FileNotFoundError(f"知识库目录不存在: {self.kb_path}")

        chunks = []
        for root, _dirs, files in os.walk(self.kb_path):
            for file in files:
                if file.endswith(".md"):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, self.kb_path)
                    file_chunks = self._parse_markdown(filepath, rel_path)
                    chunks.extend(file_chunks)

        for chunk in chunks:
            self.retriever.add_document(chunk["text"], chunk["metadata"])

        self.retriever.build_index()

    def _parse_markdown(self, filepath: str, rel_path: str) -> list[dict]:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = []
        lines = content.split("\n")
        current_section = "概述"
        current_text: list[str] = []
        current_level = 0  # 0 = document start (outside any heading)

        for line in lines:
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                level = len(header_match.group(1))
                # 只有当同级或更高级别标题出现时才切分
                # (level <= current_level 意味着同级或更高)
                if level <= current_level:
                    if current_text:
                        text = "\n".join(current_text).strip()
                        if text:
                            chunks.append({
                                "text": text,
                                "metadata": {"source": rel_path, "section": current_section},
                            })
                    current_section = header_match.group(2).strip()
                    current_text = [line]
                else:
                    # 子标题，归入当前章节
                    current_text.append(line)
                current_level = level
            else:
                current_text.append(line)

        if current_text:
            text = "\n".join(current_text).strip()
            if text:
                chunks.append({
                    "text": text,
                    "metadata": {"source": rel_path, "section": current_section},
                })

        return chunks

    def search(self, query: str, top_k: int = 3, min_score: float = 0.5, neighbor_k: int = 2) -> list[dict]:
        """
        BM25 搜索 + 邻居召回。
        
        Args:
            query: 搜索查询
            top_k: BM25 直接匹配结果数
            min_score: 最低分数阈值
            neighbor_k: 每个命中块前后各取多少个邻居
        """
        results = self.retriever.search(query, top_k=top_k)
        
        # 收集命中索引，按分数降序
        hit_indices = [(idx, score) for idx, score in results if score >= min_score]
        if not hit_indices:
            return []
        
        # 收集邻居索引（前后 neighbor_k 块，同一文件内）
        neighbor_indices: list[tuple[int, str]] = []  # (idx, source)
        for idx, _score in hit_indices:
            doc = self.retriever.corpus[idx]
            source = doc["metadata"]["source"]
            for offset in range(1, neighbor_k + 1):
                left_idx = idx - offset
                if left_idx >= 0:
                    left_doc = self.retriever.corpus[left_idx]
                    if left_doc["metadata"]["source"] == source:
                        neighbor_indices.append((left_idx, source))
                right_idx = idx + offset
                if right_idx < self.retriever.doc_count:
                    right_doc = self.retriever.corpus[right_idx]
                    if right_doc["metadata"]["source"] == source:
                        neighbor_indices.append((right_idx, source))
        
        # 合并并去重（保留命中块的排序优先级）
        seen: set[int] = set()
        output = []
        
        # 先加命中块
        for idx, score in hit_indices:
            if idx not in seen:
                seen.add(idx)
                doc = self.retriever.corpus[idx]
                output.append({
                    "text": doc["text"],
                    "source": doc["metadata"]["source"],
                    "section": doc["metadata"]["section"],
                    "score": round(score, 2),
                })
        
        # 再加邻居块（标记分数为 0，表示非直接命中）
        for idx, _source in neighbor_indices:
            if idx not in seen:
                seen.add(idx)
                doc = self.retriever.corpus[idx]
                output.append({
                    "text": doc["text"],
                    "source": doc["metadata"]["source"],
                    "section": doc["metadata"]["section"],
                    "score": 0.0,
                })
        
        return output
