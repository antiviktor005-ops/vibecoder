from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, Field

TEMPLATES = Path(__file__).with_name("templates")
env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined)


class Section(BaseModel):
    heading: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=900)


class Site(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    intro: str = Field(min_length=1, max_length=600)
    theme: Literal["forest", "ocean", "clay"]
    sections: list[Section] = Field(min_length=1, max_length=6)


def archive(site: Site) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as output:
        output.writestr("index.html", env.get_template("index.html").render(site=site))
        for name in ("style.css", "site.js"):
            output.writestr(name, (TEMPLATES / name).read_bytes())
    return buffer.getvalue()
