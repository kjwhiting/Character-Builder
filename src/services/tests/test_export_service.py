import pytest

from src.services.errors import EntityNotFoundError
from src.services.export_service import ExportService, TkClipboard


@pytest.fixture
def copied():
    return []


@pytest.fixture
def export(connection, characters, copied):
    return ExportService(connection, characters.id, copied.append)


@pytest.fixture
def filled(entities, fields):
    return entities.create_entity("Aria Vale", values={
        fields["Age"].id: "29",
        fields["Height"].id: "172",
        fields["Alive"].id: "true",
        fields["Role"].id: "Hero",
        fields["Summary"].id: "A hero",
        fields["Tags"].id: "lantern\nriver",
        fields["Traits"].id: "Brave\nShy",
    })


class TestPlainTextLayout:
    def test_each_section_is_a_heading_followed_by_name_and_value_lines(self, export, filled):
        assert export.build_plain_text(filled) == (
            "Basics\n"
            "Age: 29 years\nHeight: 172 cm\nAlive: Yes\nRole: Hero\n"
            "\n"
            "Notes\n"
            "Summary: A hero\nTags: lantern, river\nTraits: Brave, Shy\nHometown:"
        )

    def test_empty_fields_are_included_as_a_bare_label(self, export, entities, fields):
        entry = entities.create_entity("Bram")

        text = export.build_plain_text(entry)

        assert "Age:\n" in text
        assert "Hometown:" in text

    def test_an_unchecked_checkbox_reads_no(self, export, entities, fields):
        entry = entities.create_entity("Bram")

        assert "Alive: No" in export.build_plain_text(entry)

    def test_sections_and_fields_follow_their_display_order(self, export, categories, entities,
                                                              fields, filled):
        categories.reorder_categories(["Notes", "Basics"])
        categories.move_field(fields["Hometown"].id, "Notes", 0)

        text = export.build_plain_text(filled)

        assert text.startswith("Notes\nHometown:\nSummary: A hero")
        assert text.index("Basics") > text.index("Notes")

    def test_a_paragraph_with_several_lines_keeps_them(self, export, entities, fields):
        entry = entities.create_entity("A", values={fields["Summary"].id: "one\ntwo"})

        assert "Summary: one\ntwo\nTags:" in export.build_plain_text(entry)

    def test_the_entry_name_is_not_part_of_the_text(self, export, filled):
        assert "Aria Vale" not in export.build_plain_text(filled)

    def test_a_tab_with_no_fields_exports_nothing(self, connection, places):
        from src.services.entity_service import EntityService

        entry = EntityService(connection, places.id).create_entity("Old Mill")
        export = ExportService(connection, places.id, lambda text: None)

        assert export.build_plain_text(entry) == ""

    def test_another_tabs_fields_never_leak_in(self, connection, entities, fields, places):
        from src.services.category_service import CategoryService
        from src.services.entity_service import EntityService

        other = CategoryService(connection, places.id)
        other.add_category("Geography")
        other.add_field("Geography", "Terrain")
        entry = EntityService(connection, places.id).create_entity("Old Mill")
        export = ExportService(connection, places.id, lambda text: None)

        assert export.build_plain_text(entry) == "Geography\nTerrain:"


class TestMissingEntries:
    def test_an_unknown_entry_is_an_error(self, export):
        with pytest.raises(EntityNotFoundError):
            export.build_plain_text(999)

    def test_a_deleted_entry_is_an_error(self, export, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)

        with pytest.raises(EntityNotFoundError):
            export.build_plain_text(entry)


class TestCopying:
    def test_copying_sends_the_text_to_the_clipboard_and_returns_it(self, export, filled, copied):
        text = export.copy_entity(filled)

        assert copied == [text]
        assert text.startswith("Basics\nAge: 29 years")

    def test_copying_an_entry_with_nothing_filled_in_still_copies_the_labels(
        self, export, entities, fields, copied
    ):
        entry = entities.create_entity("Bram")

        export.copy_entity(entry)

        assert copied and copied[0].startswith("Basics\nAge:")

    def test_copying_a_missing_entry_leaves_the_clipboard_alone(self, export, copied):
        with pytest.raises(EntityNotFoundError):
            export.copy_entity(999)

        assert copied == []


class TestTheTkClipboard:
    def test_it_clears_then_appends_then_refreshes(self):
        calls = []

        class FakeWidget:
            def clipboard_clear(self):
                calls.append(("clear",))

            def clipboard_append(self, text):
                calls.append(("append", text))

            def update(self):
                calls.append(("update",))

        TkClipboard(FakeWidget())("hello")

        assert calls == [("clear",), ("append", "hello"), ("update",)]
