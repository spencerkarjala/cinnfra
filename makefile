KUBECTL ?= kubectl
KUSTOMIZE ?= kustomize
ENV ?= production
KUBERNETES_VERSION ?= 1.33.4

SECRETS_DIR = secrets
FIND = /usr/bin/find

lint:
	$(KUSTOMIZE) build --enable-helm overlays/$(ENV) | \
		kubeconform \
			-strict -summary \
			-kubernetes-version $(KUBERNETES_VERSION) \
			-skip CustomResourceDefinition

diff:
	$(KUSTOMIZE) build --enable-helm overlays/$(ENV) | $(KUBECTL) diff -f -

apply:
	$(KUSTOMIZE) build --enable-helm overlays/$(ENV) | $(KUBECTL) apply -f -
