SCHEMA := schema/seeker.yaml
GEN := schema/generated

.PHONY: schema lint test validate

schema:
	mkdir -p $(GEN)
	gen-shacl $(SCHEMA) > $(GEN)/seeker.shacl.ttl
	gen-owl $(SCHEMA) > $(GEN)/seeker.owl.ttl

lint:
	linkml-lint $(SCHEMA)

validate:
	seeker-decks validate
	linkml-validate -s $(SCHEMA) -C Deck decks/*.yaml

test:
	pytest
