from pydantic import BaseModel


class ProcessingResult(BaseModel):
    processed: int
    remaining: int
