include make_env

VERSION ?= 0_6


build_all : push_appserver push_frontend

build_frontend :
	cd frontend && docker build --no-cache -t $(NS)/frontend:$(VERSION) -f Dockerfile .

push_frontend : build_frontend
	docker push $(NS)/frontend:$(VERSION)

build_appserver :
	cd app-server && docker build --no-cache -t $(NS)/planespotter-app-server:$(VERSION) -f Dockerfile .

push_appserver : build_appserver
	docker push $(NS)/planespotter-app-server:$(VERSION)
