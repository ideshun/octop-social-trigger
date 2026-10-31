"""Block configured text before group input reaches either model."""

from unicodedata import normalize


class BlockedTerms:
    def __init__(self, terms):
        self.terms = tuple(normalize("NFKC", term.strip()).casefold() for term in terms)

    def matches(self, text):
        if not text:
            return False
        candidate = normalize("NFKC", text).casefold()
        return any(term in candidate for term in self.terms)

    def matches_parts(self, parts):
        texts = [getattr(part, "text", "") for part in parts]
        texts.extend(getattr(part, "filename", "") or "" for part in parts)
        texts.extend(getattr(part, "alt_text", "") or "" for part in parts)
        return self.matches("".join(texts)) or any(self.matches(text) for text in texts)

    def matches_message(self, message):
        visible_metadata = (message.metadata.get(key) for key in ("sender_name", "reply_quote_text", "reply_to_text"))
        return (
            self.matches(message.text)
            or self.matches_parts(message.content)
            or any(isinstance(text, str) and self.matches(text) for text in visible_metadata)
        )

    def filter_context(self, message):
        if self.matches_message(message):
            return False
        if message.group_context is not None:
            message.group_context.messages = [
                item
                for item in message.group_context.messages
                if not self.matches(item.text)
                and not self.matches(item.sender_name)
                and not self.matches_parts(item.content)
            ]
        return True
