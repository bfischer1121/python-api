import csv
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing_extensions import Literal, Union

# pydantic classes (using this lib for runtime type checking / validation)

DocumentStatus = Literal["SUCCEEDED", "NEEDS_REVIEW"]


class Document(BaseModel):
  id: int
  pdf_path: str
  status: DocumentStatus


class DocumentsResponse(BaseModel):
  success: Literal[True]
  documents: list[Document]


class GroupedDocumentsResponse(BaseModel):
  success: Literal[True]
  documents: dict[str, list[Document]]


class DocumentResponse(BaseModel):
  success: Literal[True]
  document: Document


# security relies on pydantic filtering posted data using this class.
# only include fields that a user might be able to change, checking authorization
class DocumentUpdate(BaseModel):
  status: Union[DocumentStatus, None] = None


# load document data

documents = []

with open("./documents.csv", mode="r", encoding="utf-8") as data:
  reader = csv.DictReader(data)

  for row in reader:
    documents.append(row)

# indexes
# cons: longer startup, higher memory use, slight complication to code
# pros: faster response times

documents_by_id = {doc['id']: doc for doc in documents}

documents_by_status = defaultdict(list)

documents_by_pdf_path = defaultdict(list)

for doc in documents:
  documents_by_status[doc["status"]].append(doc)

for doc in documents:
  documents_by_pdf_path[doc["pdf_path"]].append(doc)

duplicates = {
    path: docs
    for path, docs in documents_by_pdf_path.items() if len(docs) > 1
}

# API
# using FastAPI for less code, reasonable defaults, validations, docs, OpenAPI spec, etc
# future work would be to autogenerate TS types from the spec for end-to-end type safety

app = FastAPI()


@app.get("/")
def get_root():
  html = """
  <html>
    <head>
    <style type="text/css">
      body{
        font-family: sans-serif;
      }
      main{
        width: 300px;
        height: 100vh;
        margin: 0 auto;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: stretch;
        gap: 32px;
      }
      a{
        padding: 10px;
        text-decoration: none;
        background: #2b3245;
        color: #c2c8cc;
        border-radius: 10px;
        text-align: center;
      }
    </style>
    </head>
    <body>
      <main>
        <a href="/docs">API Docs</a>
        <a href="/openapi.json">OpenAPI Spec</a>
      </main>
    </body>
  </html>
  """

  return HTMLResponse(content=html, status_code=200)


@app.get("/documents/status/{status}", response_model=DocumentsResponse)
def get_documents(status: DocumentStatus):
  # skipped paging. opinionated, but prefer loading lots of data client-side in b2b apps
  # future work might be caching serialized json in redis
  # and client-side caching + sync for a faster startup.
  return DocumentsResponse(success=True, documents=documents_by_status[status])


@app.get("/documents/duplicates", response_model=GroupedDocumentsResponse)
def get_duplicate_documents():
  # grouped by pdf_path, but that may be a client-side concern
  return GroupedDocumentsResponse(success=True, documents=duplicates)


@app.patch("/documents/{id}", response_model=DocumentResponse)
def update_document(id: int, document: DocumentUpdate):
  old_record = documents_by_id[id]

  if old_record is None:
    raise HTTPException(status_code=404, detail="Document not found")

  # validate input
  changes = document.model_dump(exclude_unset=True)
  updated_document = Document(**old_record).model_copy(update=changes)
  new_record = updated_document.model_dump()

  # update indexes
  documents_by_status[old_record["status"]].remove(old_record)
  documents_by_status[new_record["status"]].append(new_record)
  documents_by_id[new_record["id"]] = new_record

  return DocumentResponse(success=True, document=updated_document)


if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000)

# some overall improvements would be...
# - split up into files by concern
# - configure generated spec
# - generate frontend types
# - authentication and authorization
# - switch to a db and drop indexes
# - tests
# - logging
