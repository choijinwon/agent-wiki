.PHONY: run test image deploy

run:
	python3 -m knowledge_agent.web

test:
	python3 -m unittest discover -s tests -v

image:
	docker build -t knowledge-agent:latest .

deploy:
	kubectl apply -k k8s
