.PHONY: cli psql flush-data load-data fix-data reset build build-image


cli:
	docker compose run netbox bash

shell:
	docker compose run netbox ./manage.py shell

psql:
	docker compose exec postgres psql -U netbox netbox

flush-data:
	docker compose run netbox ./manage.py flush --no-input

load-data:
	docker compose run  netbox ./manage.py loaddata /tmp/demo-data.json

fix-data:
	docker compose run netbox ./manage.py trace_paths --force --no-input

build-image:
	docker compose build netbox

clean:
	docker compose down -v

start: build-image
	docker compose up -d

stop:
	docker compose down

logs:
	docker compose logs netbox -f

migrations:
	docker compose run netbox ./manage.py makemigrations --no-input --no-header netbox_more_metrics

migrate:
	docker compose run netbox ./manage.py migrate --no-input

restart: stop start

reset: flush-data load-data fix-data

