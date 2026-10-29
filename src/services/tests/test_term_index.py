import pytest

from src.services import term_index as term_index_module
from src.services.entity_service import EntityService
from src.services.term_index import TermIndex


@pytest.fixture
def story(connection, collections, characters, places):
    people = EntityService(connection, characters.id)
    sites = EntityService(connection, places.id)
    aria = people.create_entity("Aria Vale", aliases=["Aria", "the Captain"])
    bram = people.create_entity("Bram")
    mill = sites.create_entity("Old Mill", aliases=["the Mill"])
    return {"people": people, "sites": sites, "aria": aria, "bram": bram, "mill": mill}


@pytest.fixture
def index(connection, story):
    return TermIndex(connection)


def texts(terms):
    return [t.text for t in terms]


class TestWhatGetsIndexed:
    def test_every_name_and_alternate_name_across_all_tabs_is_a_term(self, index):
        assert sorted(texts(index.all_terms()), key=str.casefold) == [
            "Aria", "Aria Vale", "Bram", "Old Mill", "the Captain", "the Mill"]

    def test_a_term_knows_its_entry_tab_colour_and_kind(self, index, story, characters):
        [term] = index.lookup("the Captain")

        assert term.kind == "alias"
        assert term.entry_id == story["aria"]
        assert term.entry_name == "Aria Vale"
        assert term.collection_id == characters.id
        assert term.collection_label == "Characters"
        assert term.color == characters.color

    def test_names_are_marked_as_names(self, index):
        assert index.lookup("Bram")[0].kind == "name"

    def test_the_index_reports_how_many_terms_it_holds(self, index):
        assert len(index) == 6

    def test_deleted_entries_are_left_out(self, connection, story):
        story["people"].delete_entity(story["bram"])

        assert "Bram" not in texts(TermIndex(connection).all_terms())

    def test_entries_in_a_trashed_tab_are_left_out(self, connection, collections, places, story):
        collections.trash_collection(places.id)

        assert "Old Mill" not in texts(TermIndex(connection).all_terms())

    def test_an_empty_project_has_an_empty_index(self, connection):
        assert len(TermIndex(connection)) == 0

    def test_the_list_returned_is_a_copy(self, index):
        terms = index.all_terms()
        terms.clear()

        assert len(index) == 6


class TestExactLookup:
    def test_lookup_ignores_case_and_surrounding_spaces(self, index):
        assert texts(index.lookup("  THE mill ")) == ["the Mill"]

    def test_lookup_ignores_accents_only_through_full_case_folding(self, connection, characters):
        EntityService(connection, characters.id).create_entity("Straße")

        assert texts(TermIndex(connection).lookup("STRASSE")) == ["Straße"]

    def test_an_unknown_word_finds_nothing(self, index):
        assert index.lookup("dragon") == []

    def test_a_word_used_in_two_tabs_finds_both(self, connection, characters, places):
        EntityService(connection, characters.id).create_entity("Ember")
        EntityService(connection, places.id).create_entity("ember")

        found = TermIndex(connection).lookup("EMBER")

        assert sorted(t.collection_label for t in found) == ["Characters", "Places"]


class TestPrefixMatching:
    def test_terms_starting_with_the_typed_letters_are_found(self, index):
        assert texts(index.prefix("ar")) == ["Aria", "Aria Vale"]

    def test_matching_ignores_case(self, index):
        assert texts(index.prefix("OLD")) == ["Old Mill"]

    def test_shorter_terms_come_first(self, connection, characters):
        people = EntityService(connection, characters.id)
        for name in ("Aria Vale", "Arbor", "Aria"):
            people.create_entity(name)

        assert texts(TermIndex(connection).prefix("ar")) == ["Aria", "Arbor", "Aria Vale"]

    def test_the_number_of_results_can_be_limited(self, index):
        assert len(index.prefix("a", limit=1)) == 1

    def test_a_blank_query_finds_nothing(self, index):
        assert index.prefix("   ") == []

    def test_accented_names_match_accented_typing(self, connection, characters):
        EntityService(connection, characters.id).create_entity("Élan")

        assert texts(TermIndex(connection).prefix("éla")) == ["Élan"]

    def test_a_query_longer_than_any_term_finds_nothing(self, index):
        assert index.prefix("aria vale and more") == []


class TestMatchingLaterWords:
    def test_a_word_inside_a_name_is_found(self, index):
        assert texts(index.word_prefix("mill")) == ["Old Mill", "the Mill"]

    def test_the_start_of_a_later_word_is_enough(self, index):
        assert "Aria Vale" in texts(index.word_prefix("va"))

    def test_the_middle_of_a_word_does_not_match(self, index):
        assert index.word_prefix("ale") == []

    def test_a_blank_query_finds_nothing(self, index):
        assert index.word_prefix("") == []


class TestSimilarSpellings:
    def test_a_slightly_misspelled_name_is_found(self, index):
        assert "Aria" in texts(index.fuzzy("aira"))

    def test_very_short_queries_are_not_guessed_at(self, index):
        assert index.fuzzy("ar") == []

    def test_unrelated_text_finds_nothing(self, index):
        assert index.fuzzy("zzzzzz") == []

    def test_an_empty_index_finds_nothing(self, connection):
        assert TermIndex(connection).fuzzy("anything") == []


class TestCombinedSearch:
    def test_prefix_matches_come_before_later_word_matches(self, index):
        assert texts(index.search("o"))[0] == "Old Mill"

    def test_each_entry_appears_only_once(self, index):
        results = index.search("ar")

        assert len([t for t in results if t.entry_id == results[0].entry_id]) == 1

    def test_a_typo_still_finds_the_entry(self, index, story):
        assert story["aria"] in [t.entry_id for t in index.search("aira")]

    def test_the_result_limit_is_respected(self, index):
        assert len(index.search("a", limit=2)) <= 2

    def test_a_blank_search_returns_nothing(self, index):
        assert index.search("  ") == []

    def test_entries_from_every_tab_can_appear_together(self, index):
        labels = {t.collection_label for t in index.search("the")}

        assert labels == {"Characters", "Places"}


class TestStayingCurrent:
    def test_refreshing_picks_up_new_entries(self, connection, index, story):
        story["people"].create_entity("Cleo")

        index.refresh()

        assert "Cleo" in texts(index.all_terms())

    def test_refreshing_drops_deleted_entries(self, index, story):
        story["people"].delete_entity(story["bram"])

        index.refresh()

        assert index.lookup("Bram") == []

    def test_refreshing_picks_up_renames_and_new_alternate_names(self, index, story):
        story["people"].update_entity(story["bram"], "Brom", aliases=["Smith"])

        index.refresh()

        assert texts(index.lookup("Smith")) == ["Smith"]
        assert index.lookup("Bram") == []

    def test_each_refresh_raises_the_version_number(self, index):
        before = index.version

        index.refresh()

        assert index.version == before + 1

    def test_without_a_refresh_the_index_keeps_its_old_view(self, index, story):
        story["people"].create_entity("Cleo")

        assert index.lookup("Cleo") == []


class TestSimilarSpellingsWithTheBuiltInMatcher:
    @pytest.fixture(autouse=True)
    def without_rapidfuzz(self, monkeypatch):
        monkeypatch.setattr(term_index_module, "process", None)

    def test_a_slightly_misspelled_name_is_still_found(self, index):
        assert "Aria" in texts(index.fuzzy("aira"))

    def test_unrelated_text_finds_nothing(self, index):
        assert index.fuzzy("zzzzzz") == []

    def test_a_name_used_in_two_tabs_is_found_in_both(self, connection, characters, places):
        EntityService(connection, characters.id).create_entity("Ember")
        EntityService(connection, places.id).create_entity("Ember")

        found = TermIndex(connection).fuzzy("embre")

        assert sorted(t.collection_label for t in found) == ["Characters", "Places"]

    def test_the_combined_search_falls_back_to_it(self, index, story):
        assert story["aria"] in [t.entry_id for t in index.search("aira")]


@pytest.mark.skipif(term_index_module.process is None, reason="rapidfuzz is not installed")
class TestSimilarSpellingsWithRapidfuzz:
    def test_a_slightly_misspelled_name_is_found(self, index):
        assert "Aria" in texts(index.fuzzy("aira"))

    def test_results_respect_the_limit(self, index):
        assert len(index.fuzzy("aria", limit=1)) <= 1
