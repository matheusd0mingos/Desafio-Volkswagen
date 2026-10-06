.PHONY: build test run clean
export UID := $(shell id -u)
export GID := $(shell id -g)

build:            ## constrói as imagens
	docker compose build

test:             ## roda os 27 testes dentro do container
	docker compose run --rm testes

run:              ## trata dados/entrada/*.xlsx → dados/saida/
	mkdir -p dados/saida
	docker compose run --rm tratar

clean:
	docker compose down --rmi local
