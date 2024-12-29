.PHONY: run docker-build

docker-build:
	docker build -t prometheus-metric-preview .

run:
	python src/app.py
