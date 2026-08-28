GHC ?= ghc
GF ?= gf
AGDA ?= agda
AGDA_RTS ?= +RTS -M8G -RTS
CUBICAL_LIB ?= $(HOME)/.cache/metonymy/cubical-v0.5
RGL_LIB ?= $(HOME)/.cache/metonymy/gf-rgl-lib
RGL_PATH = $(RGL_LIB)/alltenses:$(RGL_LIB)/prelude

.PHONY: all grammar formal formal-artifact checker engine test evaluation-test experiment \
	safecon safecon-context generated-check verbnet-generated-check verify \
	framenet-generated-check qid-fiber-test contextual-corpus-test \
	contextual-ablations reproduce clean

all: grammar formal checker engine

grammar:
	./scripts/generate_gf_lexicon.py
	$(GF) -path="$(RGL_PATH)" -make grammar/GeneratedMetonymyEng.gf

formal:
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/Soundness.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/PublicationTheorems.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/Contextual.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/ContextualTower.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/ContextualModel.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/FilteredContext.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/CompilerSoundness.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/FilteredRuntime.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/TwoTruncatedContext.agda
	$(AGDA) $(AGDA_RTS) --safe -i "$(CUBICAL_LIB)" -i formal \
		formal/Metonymy/TwoTruncatedRuntime.agda

formal-artifact: formal
	! rg -n \
		'(^|[[:space:]])(postulate|TERMINATING|NON_TERMINATING|NO_POSITIVITY)([[:space:]]|$$)' \
		formal/Metonymy --glob '*.agda'
	python3 formal/Metonymy/generate_manifest.py --check

checker:
	mkdir -p build/agda
	$(AGDA) $(AGDA_RTS) --safe --compile --no-main --compile-dir=build/agda \
		-i formal formal/Metonymy/Checker.agda
	python3 scripts/generate_malonzo_api.py \
		--source build/agda/MAlonzo/Code/Metonymy/Checker.hs \
		--output build/agda/Metonymy/CheckerAPI.hs

engine: checker
	mkdir -p build/engine build/test
	$(GHC) --make -XGHC2021 -XDerivingStrategies -O1 -Wall -Wcompat -Widentities \
		-iengine/src -ibuild/agda \
		-outputdir build/engine \
		engine/app/Main.hs \
		-o build/metonymy
	$(GHC) --make -XGHC2021 -XDerivingStrategies -O1 -Wall -Wcompat -Widentities \
		-iengine/src -ibuild/agda \
		-outputdir build/test \
		engine/test/Main.hs \
		-o build/metonymy-tests

test: all
	./build/metonymy-tests

evaluation-test:
	python3 -m unittest discover -s tests/evaluation -p 'test_*.py'

safecon: engine
	python3 scripts/evaluation/safecon.py \
		--dataset evaluation/safecon-mini/dataset.jsonl \
		--engine build/metonymy \
		--predictions build/evaluation/safecon-predictions.jsonl \
		--report build/evaluation/safecon-report.json

safecon-context: engine
	python3 scripts/evaluation/safecon.py \
		--dataset evaluation/safecon-mini/context-v2.jsonl \
		--engine build/metonymy \
		--predictions build/evaluation/safecon-context-predictions.jsonl \
		--report build/evaluation/safecon-context-report.json

generated-check:
	./scripts/generate_gf_lexicon.py
	git diff --exit-code -- \
		grammar/GeneratedMetonymy.gf \
		grammar/GeneratedMetonymyEng.gf \
		data/contextual-gf-actions.json \
		data/contextual-gf-nouns.json

framenet-generated-check:
	python3 scripts/generate_framenet_capabilities.py
	git diff --exit-code -- data/framenet-role-capabilities.json

verbnet-generated-check:
	./scripts/import_verbnet.py
	git diff --exit-code -- \
		data/verbnet-predicates.tsv \
		data/verbnet-actions.tsv \
		data/verbnet-action-roles.tsv

verify:
	$(MAKE) test
	$(MAKE) evaluation-test
	$(MAKE) safecon
	$(MAKE) safecon-context
	$(MAKE) generated-check
	$(MAKE) framenet-generated-check
	$(MAKE) qid-fiber-test

qid-fiber-test: engine
	python3 scripts/extract_wikidata_snapshot.py verify \
		--snapshot data/wikidata-qid-snapshot
	python3 scripts/evaluation/extract_qid_fibers.py \
		--dataset evaluation/qid-fiber/waterloo-dataset.jsonl \
		--engine build/metonymy \
		--output build/evaluation/waterloo-contextual-inference.jsonl
	python3 scripts/evaluation/score_qid_fibers.py \
		--inference build/evaluation/waterloo-contextual-inference.jsonl \
		--gold evaluation/qid-fiber/waterloo-gold.jsonl \
		--output build/evaluation/waterloo-contextual-report.json

contextual-corpus-test: engine
	python3 scripts/evaluation/run_contextual_corpus.py \
		--dataset evaluation/contextual-multidomain/silver-inputs.jsonl \
		--engine build/metonymy \
		--snapshot data/wikidata-openalex-snapshot \
		--output build/evaluation/contextual-silver-inference.jsonl
	python3 scripts/evaluation/score_qid_fibers.py \
		--inference build/evaluation/contextual-silver-inference.jsonl \
		--gold evaluation/contextual-multidomain/silver-gold.jsonl \
		--output build/evaluation/contextual-silver-report.json
	python3 scripts/evaluation/run_contextual_corpus.py \
		--dataset evaluation/contextual-multidomain/audited-inputs.jsonl \
		--engine build/metonymy \
		--snapshot data/wikidata-openalex-snapshot \
		--output build/evaluation/contextual-audited-inference.jsonl
	python3 scripts/evaluation/score_qid_fibers.py \
		--inference build/evaluation/contextual-audited-inference.jsonl \
		--gold evaluation/contextual-multidomain/audited-gold.jsonl \
		--output build/evaluation/contextual-audited-report.json
	python3 -c 'import json; assert json.load(open("build/evaluation/contextual-silver-report.json")) == json.load(open("evaluation/contextual-multidomain/silver-summary.json")); assert json.load(open("build/evaluation/contextual-audited-report.json")) == json.load(open("evaluation/contextual-multidomain/audited-summary.json"))'

contextual-ablations: engine
	python3 scripts/evaluation/run_contextual_ablations.py \
		--dataset evaluation/contextual-multidomain/audited-inputs.jsonl \
		--gold evaluation/contextual-multidomain/audited-gold.jsonl \
		--engine build/metonymy \
		--snapshot data/wikidata-openalex-snapshot \
		--output-dir build/evaluation/contextual-ablations
	python3 -c 'import json; assert json.load(open("build/evaluation/contextual-ablations/comparison.json")) == json.load(open("evaluation/contextual-multidomain/ablation-summary.json"))'

reproduce:
	./scripts/reproduce.sh

experiment:
	@test -n "$(EVALUATION_DATASET)" || \
		{ echo "EVALUATION_DATASET is required"; exit 2; }
	@test -n "$(EVALUATION_PREDICTIONS)" || \
		{ echo "EVALUATION_PREDICTIONS is required"; exit 2; }
	python3 scripts/evaluation/run_experiment.py \
		--dataset "$(EVALUATION_DATASET)" \
		--predictions "$(EVALUATION_PREDICTIONS)" \
		--metadata evaluation/toolchain.json \
		--output-dir build/evaluation/report

clean:
	rm -rf build dist-newstyle
	rm -f grammar/*.gfo grammar/*.pgf Metonymy.pgf GeneratedMetonymy.pgf
	rm -f formal/Metonymy/*.agdai
