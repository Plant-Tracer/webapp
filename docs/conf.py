# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

# Add project root to pythonpath
import sys

from os.path import dirname,abspath
sys.path.insert(0, dirname(dirname(abspath(__file__))))

from constants import __version__

project = 'Plant Tracer Web Application'
copyright = ' 2024 Simson Garfinkel, Steven E. Barber, JoAnn Juzefyk, Eric D. Brenner'
author = 'Simson Garfinkel, Steven E. Barber, JoAnn Juzefyk, Eric D. Brenner'
release = '1.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".txt": "markdown",
    ".md": "markdown",
}


templates_path = ['_templates']
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

#html_theme = "furo"
html_static_path = ['_static']

# autodoc

autoclass_content = "both"
autodoc_default_options = {
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
}
autodoc_typehints_format = "short"
