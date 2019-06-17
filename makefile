include make_env

VERSION ?= 0_2
FRONTEND_IMAGE_NAME ?= frontend

.PHONY: build_frontend

build_frontend :
	cd frontend && docker build -t $(NS)/$(FRONTEND_IMAGE_NAME):$(VERSION) -f Dockerfile .

push_frontend : build_frontend
	docker push $(NS)/$(FRONTEND_IMAGE_NAME):$(VERSION)

default: build_frontend