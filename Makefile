PY ?= .venv/bin/python
PROJECT ?= example
NAME ?=

.PHONY: setup setup-wallet wallet-check new list all tts record build qa clean

setup:
	./scripts/setup.sh

setup-wallet:
	./scripts/setup.sh --wallet

wallet-check:
	$(PY) scripts/wallet_inject_check.py

new:
	./scripts/new.sh $(NAME)

list:
	@ls videos

all:
	./scripts/run.sh --project $(PROJECT)

tts:
	$(PY) scripts/tts.py --project $(PROJECT)

record:
	$(PY) scripts/record.py --project $(PROJECT)

build:
	$(PY) scripts/build.py --project $(PROJECT)

qa:
	$(PY) scripts/qa.py --project $(PROJECT)

clean:
	rm -rf videos/*/audio videos/*/clips videos/*/work videos/*/build videos/*/qa
