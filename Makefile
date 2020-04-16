export PYTHONPATH := .:$(CURDIR)/modules/mysql-connector-python:$(CURDIR)/resources/lib:$(CURDIR)/test
PYTHON := python

name = $(shell xmllint --xpath 'string(/addon/@id)' addon.xml)
version = $(shell xmllint --xpath 'string(/addon/@version)' addon.xml)
git_branch = $(shell git rev-parse --abbrev-ref HEAD)
git_hash = $(shell git rev-parse --short HEAD)

zip_name = $(name)-$(version)-$(git_branch)-$(git_hash).zip
include_files = addon.py addon.xml LICENSE.txt modules/ README.md resources/ service.py
include_paths = $(patsubst %,$(name)/%,$(include_files))
exclude_files = \*.new \*.orig \*.pyc \*.pyo
zip_dir = $(name)/

languages = $(filter-out en_gb, $(patsubst resources/language/resource.language.%, %, $(wildcard resources/language/*)))

blue = \e[1;34m
white = \e[1;37m
reset = \e[0m

all: check test build
zip: build
test: check test-unit test-service test-run

check: check-tox check-pylint check-translations

check-tox:
	@echo -e "$(white)=$(blue) Starting sanity tox test$(reset)"
	$(PYTHON) -m tox -q -e

check-pylint:
	@echo -e "$(white)=$(blue) Starting sanity pylint test$(reset)"
	$(PYTHON) -m pylint resources/lib/ tests/

check-translations:
	@echo -e "$(white)=$(blue) Starting language test$(reset)"
	@-$(foreach lang,$(languages), \
		msgcmp resources/language/resource.language.$(lang)/strings.po resources/language/resource.language.en_gb/strings.po; \
	)

check-addon: clean
	@echo -e "$(white)=$(blue) Starting sanity addon tests$(reset)"
	kodi-addon-checker --branch=leia

unit: test-unit
run: test-run

test-unit: clean
	@echo -e "$(white)=$(blue) Starting unit tests$(reset)"
	$(PYTHON) -m unittest discover

test-run:
	@echo -e "$(white)=$(blue) Run CLI$(reset)"
	coverage run -a tests/run.py /action/purge_cache/
	coverage run -a tests/run.py /action/purge_cache/?on_disk=True
	coverage run -a service.py &
	sleep 10
	coverage run -a tests/run.py /directory/root
	coverage run -a tests/run.py /directory/profiles
	coverage run -a tests/run.py /directory/home
	coverage run -a tests/run.py /directory/video_list_sorted/myList/queue
	coverage run -a tests/run.py /directory/video_list_sorted/newRelease/newRelease
	coverage run -a tests/run.py /directory/video_list/continueWatching/continueWatching
	coverage run -a tests/run.py /directory/video_list/chosenForYou/topTen
	coverage run -a tests/run.py /directory/video_list/recentlyAdded/1592210
	coverage run -a tests/run.py /directory/show/80057281/
	coverage run -a tests/run.py /directory/show/80057281/season/80186799/
	coverage run -a tests/run.py /directory/genres/tvshows/83/
	coverage run -a tests/run.py /directory/genres/movies/34399/
	coverage run -a tests/run.py /directory/search/search/cool
	coverage run -a tests/run.py /directory/exported/exported
	pkill -ef service.py

build: clean
	@echo -e "$(white)=$(blue) Building new package$(reset)"
	@rm -f ../$(zip_name)
	cd ..; zip -r $(zip_name) $(include_paths) -x $(exclude_files)
	@echo -e "$(white)=$(blue) Successfully wrote package as: $(white)../$(zip_name)$(reset)"

clean:
	@echo -e "$(white)=$(blue) Cleaning up$(reset)"
	find . -name '*.py[cod]' -type f -delete
	find . -name __pycache__ -type d -delete
	rm -rf .pytest_cache/ .tox/
	rm -f *.log
