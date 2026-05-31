"""
Eager loading (prefetch) テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, ForeignKey, has_many, has_one, belongs_to


# ── モデル定義 ───────────────────────────────────────────────


class PfAuthor(Model):
    name    = StrColumn(nullable=False)
    posts   = has_many("PfPost",    foreign_key="author_id")
    profile = has_one("PfProfile",  foreign_key="author_id")

    class Meta:
        table_name = "pf_author"


class PfPost(Model):
    title     = StrColumn(nullable=False)
    author_id = ForeignKey(PfAuthor, nullable=True)
    author    = belongs_to(PfAuthor, foreign_key="author_id")

    class Meta:
        table_name = "pf_post"


class PfProfile(Model):
    bio       = StrColumn(nullable=True)
    author_id = ForeignKey(PfAuthor, nullable=True)

    class Meta:
        table_name = "pf_profile"


# ── フィクスチャ ──────────────────────────────────────────────


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(PfAuthor)
    await eng.create_table(PfPost)
    await eng.create_table(PfProfile)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    alice = await PfAuthor.create(name="Alice")
    bob   = await PfAuthor.create(name="Bob")
    await PfPost.create(title="Alice Post 1", author_id=alice.id)
    await PfPost.create(title="Alice Post 2", author_id=alice.id)
    await PfPost.create(title="Bob Post 1",   author_id=bob.id)
    await PfProfile.create(bio="Alice's bio", author_id=alice.id)
    return {"alice": alice, "bob": bob}


# ── belongs_to ───────────────────────────────────────────────


class TestPrefetchBelongsTo:
    async def test_prefetch_belongs_to_returns_correct_author(self, seeded):
        posts = await PfPost.all().prefetch("author")
        for post in posts:
            author = await post.author
            assert author is not None
            assert isinstance(author, PfAuthor)

    async def test_prefetch_belongs_to_no_extra_queries(self, seeded, monkeypatch):
        """キャッシュ後は _fetch が呼ばれないことを確認する。"""
        posts = await PfPost.all().prefetch("author")

        # キャッシュ確認: _prefetch_cache["author"] が存在する
        for post in posts:
            assert hasattr(post, "_prefetch_cache")
            assert "author" in post._prefetch_cache

        # 2回目アクセスは同じオブジェクトを返す（キャッシュ）
        author_first  = await posts[0].author
        author_second = await posts[0].author
        assert author_first is author_second

    async def test_prefetch_belongs_to_null_fk(self, engine):
        """FK が NULL のインスタンスは None を返す。"""
        await PfPost.create(title="Orphan", author_id=None)
        posts = await PfPost.where(PfPost.title == "Orphan").prefetch("author")
        author = await posts[0].author
        assert author is None

    async def test_prefetch_belongs_to_grouping(self, seeded):
        """Alice の投稿は Alice を、Bob の投稿は Bob を返す。"""
        posts = await PfPost.all().order_by(PfPost.title.asc).prefetch("author")
        mapping = {p.title: (await p.author).name for p in posts}
        assert mapping["Alice Post 1"] == "Alice"
        assert mapping["Alice Post 2"] == "Alice"
        assert mapping["Bob Post 1"]   == "Bob"


# ── has_many ─────────────────────────────────────────────────


class TestPrefetchHasMany:
    async def test_prefetch_has_many_returns_list(self, seeded):
        authors = await PfAuthor.all().prefetch("posts")
        alice = next(a for a in authors if a.name == "Alice")
        posts = await alice.posts
        assert isinstance(posts, list)
        assert len(posts) == 2

    async def test_prefetch_has_many_correct_count(self, seeded):
        authors = await PfAuthor.all().prefetch("posts")
        bob = next(a for a in authors if a.name == "Bob")
        posts = await bob.posts
        assert len(posts) == 1
        assert posts[0].title == "Bob Post 1"

    async def test_prefetch_has_many_empty_relation(self, engine):
        """関連なしの著者は空リストを返す。"""
        await PfAuthor.create(name="NoPostAuthor")
        authors = await PfAuthor.where(PfAuthor.name == "NoPostAuthor").prefetch("posts")
        posts = await authors[0].posts
        assert posts == []


# ── has_one ──────────────────────────────────────────────────


class TestPrefetchHasOne:
    async def test_prefetch_has_one_returns_single(self, seeded):
        authors = await PfAuthor.all().prefetch("profile")
        alice = next(a for a in authors if a.name == "Alice")
        profile = await alice.profile
        assert profile is not None
        assert profile.bio == "Alice's bio"

    async def test_prefetch_has_one_none_when_absent(self, seeded):
        """プロフィールがない著者は None を返す。"""
        authors = await PfAuthor.all().prefetch("profile")
        bob = next(a for a in authors if a.name == "Bob")
        profile = await bob.profile
        assert profile is None


# ── エラーケース ──────────────────────────────────────────────


class TestPrefetchErrors:
    async def test_prefetch_unknown_relation_raises(self, engine):
        await PfAuthor.create(name="Test")
        with pytest.raises(AttributeError, match="no_such_rel"):
            await PfAuthor.all().prefetch("no_such_rel")

    async def test_prefetch_empty_queryset_no_error(self, engine):
        """結果が空でもエラーにならない。"""
        posts = await PfPost.all().prefetch("author")
        assert posts == []
