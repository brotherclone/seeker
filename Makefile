SCHEMA := schema/seeker.yaml
GEN := schema/generated

.PHONY: setup schema lint test validate

setup:
	uv sync

schema:
	mkdir -p $(GEN)
	uv run gen-shacl $(SCHEMA) > $(GEN)/seeker.shacl.ttl
	uv run gen-owl $(SCHEMA) > $(GEN)/seeker.owl.ttl

lint:
	uv run linkml-lint $(SCHEMA)

validate:
	uv run seeker-decks validate
	uv run linkml-validate -s $(SCHEMA) -C Deck decks/*.yaml

test:
	uv run pytest
