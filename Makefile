ENVS := flake8,py27,py36
export PYTHONPATH := .:$(CURDIR)/modules/mysql-connector-python:$(CURDIR)/resources/lib:$(CURDIR)/test
addon_xml := addon.xml

# Collect information to build as sensible package name
name = $(shell xmllint --xpath 'string(/addon/@id)' $(addon_xml))
version = $(shell xmllint --xpath 'string(/addon/@version)' $(addon_xml))
git_branch = $(shell git rev-parse --abbrev-ref HEAD)
git_hash = $(shell git rev-parse --short HEAD)

zip_name = $(name)-$(version)-$(git_branch)-$(git_hash).zip
include_files = addon.py addon.xml LICENSE.txt modules/ README.md resources/ service.py
include_paths = $(patsubst %,$(name)/%,$(include_files))
exclude_files = \*.new \*.orig \*.pyc \*.pyo
zip_dir = $(name)/

blue = \e[1;34m
white = \e[1;37m
reset = \e[0m

all: clean test zip

clean:
	find . -name '*.pyc' -type f -delete
	find . -name '*.pyo' -type f -delete
	find . -name __pycache__ -type d -delete
	rm -rf .pytest_cache/ .tox/

test: sanity unit

sanity: tox pylint

tox:
	@echo -e "$(white)=$(blue) Starting sanity tox test$(reset)"
	tox -q -e $(ENVS)

pylint:
	@echo -e "$(white)=$(blue) Starting sanity pylint test$(reset)"
	pylint resources/lib/ test/

addon: clean
	@echo -e "$(white)=$(blue) Starting sanity addon tests$(reset)"
	kodi-addon-checker . --branch=leia

unit:
	@echo -e "$(white)=$(blue) Starting unit tests$(reset)"
	python -m unittest discover

run:
	@echo -e "$(white)=$(blue) Run CLI$(reset)"
	coverage run -a service.py &
	sleep 10
	coverage run -a test/run.py /action/purge_cache/
	coverage run -a test/run.py /action/purge_cache/?on_disk=True
	coverage run -a test/run.py /directory/root
	coverage run -a test/run.py /directory/profiles
	coverage run -a test/run.py /directory/home
	coverage run -a test/run.py /directory/video_list_sorted/myList/queue
	coverage run -a test/run.py /directory/video_list_sorted/newRelease/newRelease
	coverage run -a test/run.py /directory/video_list/continueWatching/continueWatching
	coverage run -a test/run.py /directory/video_list/chosenForYou/topTen
	coverage run -a test/run.py /directory/video_list/recentlyAdded/1592210
	coverage run -a test/run.py /directory/show/80057281/
	coverage run -a test/run.py /directory/show/80057281/season/80186799/
	coverage run -a test/run.py /directory/genres/tvshows/83/
	coverage run -a test/run.py /directory/genres/movies/34399/
	coverage run -a test/run.py /directory/search/search/cool
	coverage run -a test/run.py /directory/exported/exported
	pkill -ef service.py

zip: clean
	@echo -e "$(white)=$(blue) Building new package$(reset)"
	@rm -f ../$(zip_name)
	cd ..; zip -r $(zip_name) $(include_paths) -x $(exclude_files)
	@echo -e "$(white)=$(blue) Successfully wrote package as: $(white)../$(zip_name)$(reset)"
