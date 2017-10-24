.PHONY: all test clean docs clean-pyc clean-report clean-docs clean-coverage rere
.DEFAULT_GOAL := all

SPHINXBUILD = sphinx-build
SPHINXPROJ = pluginvideonetflix
BUILDDIR = ./_build
SOURCEDIR = ./resources/lib
TEST_DIR = ./resources/test
COVERAGE_FILE = ./.coverage
COVERAGE_DIR = ./coverage
REPORT_DIR = ./report
DOCS_DIR = ./docs
FLAKE_FILES = ./addon.py ./service.py ./setup.py ./resources/lib/utils.py ./resources/lib/MSLHttpRequestHandler.py ./resources/lib/NetflixHttpRequestHandler.py ./resources/lib/Navigation.py ./resources/lib/kodi/Dialogs.py
RADON_FILES = resources/lib/*.py resources/lib/kodi/*.py ./addon.py ./service.py
PYLINT_FILES = addon service setup resources.lib.kodi.Dialogs resources.lib.MSLHttpRequestHandler resources.lib.NetflixHttpRequestHandler resources.lib.utils
LINT_REPORT_FILE = ./report/lint.html
TEST_OPTIONS = -s --cover-package=resources.lib.utils --cover-package=resources.lib.NetflixSession  --cover-package=resources.lib.Navigation --cover-package=resources.lib.MSL --cover-package=resources.lib.KodiHelper --cover-package=resources.lib.kodi.Dialogs --cover-package=resources.lib.Library --cover-package=resources.lib.KodiHelper --cover-package=resources.lib.Library --cover-package=resources.lib.NetflixHttpRequestHandler --cover-package=resources.lib.NetflixHttpSubRessourceHandler --cover-erase --with-coverage --cover-branches
I18N_FILES = resources/language/**/*.po

all: clean lint test docs

clean: clean-pyc clean-report clean-docs clean-coverage

clean-docs:
	rm -rf $(BUILDDIR) || exit 0

clean-pyc:
		find . -name '*.pyc' -exec rm {} +
		find . -name '*.pyo' -exec rm {} +

clean-report:
		rm -rf $(REPORT_DIR) || exit 0
		mkdir $(REPORT_DIR)

clean-coverage:
		rm $(COVERAGE_FILE) || exit 0
		rm -rf $(COVERAGE_DIR) || exit 0
		mkdir $(COVERAGE_DIR)

lint:
		flake8 --filename=$(FLAKE_FILES)
		pylint $(PYLINT_FILES) --ignore=test,UniversalAnalytics || exit 0		
		pylint $(PYLINT_FILES) --ignore=test,UniversalAnalytics --output-format=html > $(LINT_REPORT_FILE)
		radon cc $(RADON_FILES)
		dennis-cmd lint $(I18N_FILES)
		rst-lint docs/index.rst --level=severe		
		yamllint .travis.yml .codeclimate.yml

docs:
	@$(SPHINXBUILD) $(DOCS_DIR) $(BUILDDIR) -T -c ./docs

test:
		nosetests $(TEST_DIR) $(TEST_OPTIONS) --cover-html --cover-html-dir=$(COVERAGE_DIR)

rere:
	codeclimate-test-reporter

help:
		@echo "    clean-pyc"
		@echo "        Remove python artifacts."
		@echo "    clean-report"
		@echo "        Remove coverage/lint report artifacts."
		@echo "    clean-docs"
		@echo "        Remove sphinx artifacts."
		@echo "    clean-coverage"
		@echo "        Remove code coverage artifacts."
		@echo "    clean"
		@echo "        Calls all clean tasks."		
		@echo "    lint"
		@echo "        Check style with flake8, pylint & radon"
		@echo "    test"
		@echo "        Run unit tests"
		@echo "    docs"
		@echo "        Generate sphinx docs"		
