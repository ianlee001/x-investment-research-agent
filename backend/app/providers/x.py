import re
from urllib.parse import quote

from app.providers.http import ProviderError, ProviderHTTP

POST_FIELDS = (
    "created_at,author_id,public_metrics,referenced_tweets,entities,edit_history_tweet_ids,note_tweet"
)


class XProvider:
    def __init__(self, http: ProviderHTTP):
        self.http = http

    async def request(self, path: str, params=None, ttl=0):
        key = self.http.settings.x_bearer_token.get_secret_value()
        if not key:
            raise ProviderError("x", "not_configured")
        return await self.http.get(
            "x",
            "https://api.x.com/2" + path,
            params=params,
            headers={"Authorization": "Bearer " + key},
            ttl=ttl,
        )

    async def user(self, username: str):
        username = username.lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
            raise ProviderError("x", "invalid_username")
        result = await self.request(
            f"/users/by/username/{quote(username)}",
            {"user.fields": "description,profile_image_url,public_metrics"},
            ttl=3600,
        )
        if not result.get("data"):
            raise ProviderError("x", "user_unavailable")
        return result["data"]

    async def posts(self, user_id: str, *, since_id=None, pagination_token=None, max_results=20):
        if not user_id.isdigit():
            raise ProviderError("x", "invalid_user_id")
        params = {
            "max_results": max(5, min(100, max_results)),
            "tweet.fields": POST_FIELDS,
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        if since_id:
            params["since_id"] = since_id
        if pagination_token:
            params["pagination_token"] = pagination_token
        return await self.request(f"/users/{user_id}/tweets", params)

    async def get_posts(self, ids: list[str]):
        if not ids or len(ids) > 100 or any(not value.isdigit() for value in ids):
            raise ProviderError("x", "invalid_post_ids")
        return await self.request(
            "/tweets",
            {
                "ids": ",".join(ids),
                "tweet.fields": POST_FIELDS,
                "expansions": "author_id",
                "user.fields": "username,name",
            },
        )

    async def search(self, query: str):
        if not self.http.settings.x_search_enabled:
            raise ProviderError("x", "search_disabled_use_tracked_posts_or_enable_X_SEARCH_ENABLED")
        return await self.request(
            "/tweets/search/recent",
            {
                "query": query[:512],
                "max_results": 10,
                "tweet.fields": POST_FIELDS,
                "expansions": "author_id",
                "user.fields": "username",
            },
            ttl=300,
        )

    @staticmethod
    def normalize(response: dict, default_username=""):
        users = {row["id"]: row["username"] for row in response.get("includes", {}).get("users", [])}
        rows = response.get("data", [])
        if isinstance(rows, dict):
            rows = [rows]
        normalized = []
        for row in rows:
            text = row.get("note_tweet", {}).get("text") or row.get("text", "")
            normalized.append(
                {
                    "id": str(row["id"]),
                    "author_id": str(row.get("author_id", "")),
                    "username": users.get(row.get("author_id"), default_username),
                    "text": text,
                    "created_at": row.get("created_at"),
                    "metrics": row.get("public_metrics", {}),
                    "references": row.get("referenced_tweets", []),
                    "edit_history_ids": [str(v) for v in row.get("edit_history_tweet_ids", [row["id"]])],
                    "tickers": sorted(set(re.findall(r"\$([A-Z][A-Z0-9.]{0,9})\b", text))),
                }
            )
        return normalized

    @staticmethod
    def document(post: dict):
        return {
            "title": f"@{post['username']} · X",
            "url": f"https://x.com/{post['username'] or 'i'}/status/{post['id']}",
            "excerpt": post["text"],
            "source_type": "x",
            "published_at": post["created_at"],
            "metadata": {"post_id": post["id"], "author_id": post["author_id"], "username": post["username"]},
        }
