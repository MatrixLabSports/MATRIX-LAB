from __future__ import annotations

import ast
import base64
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "infra/aws/r8_3r6/authority_service/authority_service.py"
REQUIREMENTS_PATH = ROOT / "infra/aws/r8_3r6/authority_service/requirements.txt"
DESIGN_PATH = ROOT / "docs/FOOTBALL_BOUNDED_LIVE_EXECUTOR_R8_3R6_AUTHORITY_SERVICE_SOURCE_DESIGN.md"
IMPL_DOC_PATH = ROOT / "docs/FOOTBALL_BOUNDED_LIVE_EXECUTOR_R8_3R6_AUTHORITY_SERVICE_SOURCE_IMPLEMENTATION.md"

spec = importlib.util.spec_from_file_location("matrix_r836_authority_service_under_test", SOURCE_PATH)
assert spec is not None and spec.loader is not None
auth = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = auth
spec.loader.exec_module(auth)

PARITY_RECEIPTS_B64 = [
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiJiM2Q1MmJmN2FmYWE1NTljOWI5Y2UyMjA5YjgyODIxZDIyNzRkYjc4MmM1MzJjOWFhNWFiYzJmOWZiYTlmMGRiIiwiY29udHJvbF9pZCI6bnVsbCwiY3JlYXRlZF9hdCI6IjIwMjYtMDgtMjVUMjM6MDA6MDArMDA6MDAiLCJkYXRhYmFzZV9pbnN0YW5jZV9pZCI6IjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIiLCJkb21haW5fc2VwYXJhdG9yIjoibWF0cml4LmMyLXI4LTNyNi1leHRlcm5hbC1pbnRlZ3JpdHktcm9vdC8xIiwibG9jYWxfY29udHJvbF9zdGF0ZV92ZXJzaW9uIjpudWxsLCJsb2NhbF9zY2hlbWFfdXNlcl92ZXJzaW9uIjo4NywibG9jYWxfdHJhbnNpdGlvbl9ldmVudF9pZCI6bnVsbCwibG9jYWxfdHJhbnNpdGlvbl9ldmVudF9zaGEyNTYiOm51bGwsImxvY2FsX3RyYW5zaXRpb25fc2VxdWVuY2UiOm51bGwsIm1ldGFkYXRhIjp7ImJhY2tlbmRfcHJvZmlsZSI6IkFXU19EVUFMX0JPVU5EQVJZX1MzX09CSkVDVF9MT0NLX0NPTVBMSUFOQ0VfS01TX0VEMjU1MTlfVjEiLCJib290c3RyYXBfcHVibGljX2tleV9iNjQiOiIrZThzNzJ4ZVdNcVdiWE9WWUpkblNnNmVCQ2tJZmNYZEpHeW1jRE4wNzRJPSIsImJvb3RzdHJhcF9wdWJsaWNfa2V5X2ZpbmdlcnByaW50IjoiNWIxMzMxZDJlMmJmMGNhY2RmZGEwNmE1NDU2OWE3MTZkY2U2MjYzMWJhMzc1Mzk3ZWFhYTZlYTU2YjM1YmIyNyIsImJvb3RzdHJhcF9zaWduZXJfa2V5X2lkIjoiZWQyNTUxOTo1YjEzMzFkMmUyYmYwY2FjZGZkYTA2YTU0NTY5YTcxNmRjZTYyNjMxYmEzNzUzOTdlYWFhNmVhNTZiMzViYjI3IiwiY29udHJvbGxlZF9saXZlX2FkbWlzc2libGUiOmZhbHNlLCJnZW5lc2lzX3J1bl9zdGF0ZSI6W10sImdlbmVzaXNfdHJhbnNpdGlvbl9ldmVudHMiOltdLCJsb2NhbF9zbmFwc2hvdF9zaGEyNTYiOiI1MzBjNzRmOWNmZjQyNTY0NmFiZmE5ZmM4YjRiMmQ3MmRlOWZlNjNhM2FlOTU4NGZjZTJkMWNkNzc0MDgzNDAyIn0sIm9wZXJhdGlvbl9pZCI6ImFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWEiLCJwcmV2aW91c19yZWNlaXB0X2lkIjpudWxsLCJwcmV2aW91c19yZWNlaXB0X3NoYTI1NiI6bnVsbCwicHJvamVjdF9kb21haW5faWQiOiJtYXRyaXguYzIiLCJyZWNlaXB0X2lkIjoiMTE5YmQ1NTcxMTE1ZTZmNDdmNGNkODkzNDQ2YTc3M2I3YTU5MTM3MGE2MDcyYzRkZjE2NmU0MWI3NTY0MDE2MSIsInJlY2VpcHRfcHJvdG9jb2xfdmVyc2lvbiI6MSwicmVjZWlwdF90eXBlIjoiUk9PVF9HRU5FU0lTIiwicm9vdF9zZXF1ZW5jZSI6MSwicm9vdF9zdG9yZV9pZCI6IjExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEiLCJydW5faWQiOm51bGwsInNpZ25hdHVyZV9iNjQiOiJHZktmSVhTUUQxZnpoa3NJTWYva1lqYzkzdFBsbGxhbUR0NnJOYzRzcWJxa3g2T2dMT1pLMzNZWHFORXBsY2J2U2xHTnNEZ2N3MEdpRlRyODk4K1JBdz09Iiwic2lnbmVyX2tleV9pZCI6ImVkMjU1MTk6NWIxMzMxZDJlMmJmMGNhY2RmZGEwNmE1NDU2OWE3MTZkY2U2MjYzMWJhMzc1Mzk3ZWFhYTZlYTU2YjM1YmIyNyIsInNwb3J0X2lkIjoiZm9vdGJhbGwifQo=",
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiI1NDdjNmI3MzIwNGFhZjM4OTA1NWFiNjY1NTc3MWVmMDY3ZDQ2MWQ3ZGEyYmQyNDQ5NmVmMTY4MjY3YmQwNjU5IiwiY29udHJvbF9pZCI6IjMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMiLCJjcmVhdGVkX2F0IjoiMjAyNi0wOC0yNVQyMzowMDowMSswMDowMCIsImRhdGFiYXNlX2luc3RhbmNlX2lkIjoiMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMiIsImRvbWFpbl9zZXBhcmF0b3IiOiJtYXRyaXguYzItcjgtM3I2LWV4dGVybmFsLWludGVncml0eS1yb290LzEiLCJsb2NhbF9jb250cm9sX3N0YXRlX3ZlcnNpb24iOjAsImxvY2FsX3NjaGVtYV91c2VyX3ZlcnNpb24iOjg3LCJsb2NhbF90cmFuc2l0aW9uX2V2ZW50X2lkIjoiNTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NSIsImxvY2FsX3RyYW5zaXRpb25fZXZlbnRfc2hhMjU2IjoiNjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NiIsImxvY2FsX3RyYW5zaXRpb25fc2VxdWVuY2UiOjEsIm1ldGFkYXRhIjp7ImV4cGVjdGVkX25leHRfc3RhdGUiOiJJTl9QUk9HUkVTUyIsImV4cGVjdGVkX291dGNvbWUiOiJTVEFURV9UUkFOU0lUSU9OX0NPTU1JVFRFRCIsImV4cGVjdGVkX3ByaW9yX3N0YXRlIjoiUExBTk5FRCIsImV4cGVjdGVkX3N0YXRlX3ZlcnNpb25fYWZ0ZXIiOjEsImV4cGVjdGVkX3N0YXRlX3ZlcnNpb25fYmVmb3JlIjowfSwib3BlcmF0aW9uX2lkIjoiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYiIsInByZXZpb3VzX3JlY2VpcHRfaWQiOiIxMTliZDU1NzExMTVlNmY0N2Y0Y2Q4OTM0NDZhNzczYjdhNTkxMzcwYTYwNzJjNGRmMTY2ZTQxYjc1NjQwMTYxIiwicHJldmlvdXNfcmVjZWlwdF9zaGEyNTYiOiJhYTAxOTlmZTM3MzBjZWYzMWZhMjk3YzNmMmI4ZWE4MWI5NDQzMGEzMmY1NGY1NWUyYWE3Y2VlYzRhZWRkZTIzIiwicHJvamVjdF9kb21haW5faWQiOiJtYXRyaXguYzIiLCJyZWNlaXB0X2lkIjoiZGYxNWZlYTIzNzE0OTRkOGE4YjJlNTU4NzRjNzdlYzYwOTQ1MzEzODJjZmE4YTUyNTJlMjcxNDkwMzE0Yzc5MSIsInJlY2VpcHRfcHJvdG9jb2xfdmVyc2lvbiI6MSwicmVjZWlwdF90eXBlIjoiUk9PVF9QUkVQQVJFRCIsInJvb3Rfc2VxdWVuY2UiOjIsInJvb3Rfc3RvcmVfaWQiOiIxMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExIiwicnVuX2lkIjoiNDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCIsInNpZ25hdHVyZV9iNjQiOiJ6Nkk2aC9ZU1dQdVZIUjhhTURCK1JmdDMzLzgwU2xnWUFGRzIxVkx4OE1rN0JTZGZ2M1ljeXlHMHA0UE9kRG8va2ZvemhtUnp2c3JXcU9qYUNScHZEdz09Iiwic2lnbmVyX2tleV9pZCI6ImVkMjU1MTk6NWIxMzMxZDJlMmJmMGNhY2RmZGEwNmE1NDU2OWE3MTZkY2U2MjYzMWJhMzc1Mzk3ZWFhYTZlYTU2YjM1YmIyNyIsInNwb3J0X2lkIjoiZm9vdGJhbGwifQo=",
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiJhYjMyZTkxNTBmN2RjODlhYmQ1ZmI5M2MyOWVjYTZkZDJlYWM3NmVkNGMwZTY1NmQxMGMwMGM5MWQwYWU5MzZlIiwiY29udHJvbF9pZCI6IjMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMiLCJjcmVhdGVkX2F0IjoiMjAyNi0wOC0yNVQyMzowMDowMiswMDowMCIsImRhdGFiYXNlX2luc3RhbmNlX2lkIjoiMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMiIsImRvbWFpbl9zZXBhcmF0b3IiOiJtYXRyaXguYzItcjgtM3I2LWV4dGVybmFsLWludGVncml0eS1yb290LzEiLCJsb2NhbF9jb250cm9sX3N0YXRlX3ZlcnNpb24iOjAsImxvY2FsX3NjaGVtYV91c2VyX3ZlcnNpb24iOjg3LCJsb2NhbF90cmFuc2l0aW9uX2V2ZW50X2lkIjoiNTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NSIsImxvY2FsX3RyYW5zaXRpb25fZXZlbnRfc2hhMjU2IjoiNjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NiIsImxvY2FsX3RyYW5zaXRpb25fc2VxdWVuY2UiOjEsIm1ldGFkYXRhIjp7InByZXBhcmVkX3JlY2VpcHRfaWQiOiJkZjE1ZmVhMjM3MTQ5NGQ4YThiMmU1NTg3NGM3N2VjNjA5NDUzMTM4MmNmYThhNTI1MmUyNzE0OTAzMTRjNzkxIiwicHJlcGFyZWRfcmVjZWlwdF9zaGEyNTYiOiIzNjQxMDA2MzRmMzU4YjEyMjRhZmEwNGU3NDZhYmIyYTBlOWM0YTU1MzkyZGFhZmNmMzI1Y2VjN2Q3NjQ1OTRlIn0sIm9wZXJhdGlvbl9pZCI6ImJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmIiLCJwcmV2aW91c19yZWNlaXB0X2lkIjoiZGYxNWZlYTIzNzE0OTRkOGE4YjJlNTU4NzRjNzdlYzYwOTQ1MzEzODJjZmE4YTUyNTJlMjcxNDkwMzE0Yzc5MSIsInByZXZpb3VzX3JlY2VpcHRfc2hhMjU2IjoiMzY0MTAwNjM0ZjM1OGIxMjI0YWZhMDRlNzQ2YWJiMmEwZTljNGE1NTM5MmRhYWZjZjMyNWNlYzdkNzY0NTk0ZSIsInByb2plY3RfZG9tYWluX2lkIjoibWF0cml4LmMyIiwicmVjZWlwdF9pZCI6IjE5MTk5NDdhZjY3NTljMmIxMmQxNTc4M2RhNjdjZmM2OGViMDExNTQ5YjYwZTk1NTQyZTBmOTJkZTZkYTgzOWMiLCJyZWNlaXB0X3Byb3RvY29sX3ZlcnNpb24iOjEsInJlY2VpcHRfdHlwZSI6IlJPT1RfQ09NTUlUVEVEIiwicm9vdF9zZXF1ZW5jZSI6Mywicm9vdF9zdG9yZV9pZCI6IjExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEiLCJydW5faWQiOiI0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0Iiwic2lnbmF0dXJlX2I2NCI6IjNpdjJ1VG9DUnJvMXA3YzFVd1hxY1VXT0FuZ3o4a0N3T1VxVmZtOG1lTGR5d3RKZW9ONHNzTUx2MkNpOVhQK3FMRmtwQ3pVUk91ZFRXcTh0d2JOQ0RBPT0iLCJzaWduZXJfa2V5X2lkIjoiZWQyNTUxOTo1YjEzMzFkMmUyYmYwY2FjZGZkYTA2YTU0NTY5YTcxNmRjZTYyNjMxYmEzNzUzOTdlYWFhNmVhNTZiMzViYjI3Iiwic3BvcnRfaWQiOiJmb290YmFsbCJ9Cg==",
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiI4NTNjZjYyNjA5MDIwYmZlM2YwMGRjNmVmYTZiZGVlZjY3ODRlYmJhODZjOWFkYWIxNTdmOTZiYTcwYWZkMzZmIiwiY29udHJvbF9pZCI6IjMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMiLCJjcmVhdGVkX2F0IjoiMjAyNi0wOC0yNVQyMzowMDowMyswMDowMCIsImRhdGFiYXNlX2luc3RhbmNlX2lkIjoiMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMiIsImRvbWFpbl9zZXBhcmF0b3IiOiJtYXRyaXguYzItcjgtM3I2LWV4dGVybmFsLWludGVncml0eS1yb290LzEiLCJsb2NhbF9jb250cm9sX3N0YXRlX3ZlcnNpb24iOjEsImxvY2FsX3NjaGVtYV91c2VyX3ZlcnNpb24iOjg3LCJsb2NhbF90cmFuc2l0aW9uX2V2ZW50X2lkIjoiNzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3NyIsImxvY2FsX3RyYW5zaXRpb25fZXZlbnRfc2hhMjU2IjoiODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4ODg4OCIsImxvY2FsX3RyYW5zaXRpb25fc2VxdWVuY2UiOjIsIm1ldGFkYXRhIjp7ImV4cGVjdGVkX25leHRfc3RhdGUiOiJJTl9QUk9HUkVTUyIsImV4cGVjdGVkX291dGNvbWUiOiJTVEFURV9UUkFOU0lUSU9OX1JFSkVDVEVEIiwiZXhwZWN0ZWRfcHJpb3Jfc3RhdGUiOiJJTl9QUk9HUkVTUyIsImV4cGVjdGVkX3N0YXRlX3ZlcnNpb25fYWZ0ZXIiOjEsImV4cGVjdGVkX3N0YXRlX3ZlcnNpb25fYmVmb3JlIjoxfSwib3BlcmF0aW9uX2lkIjoiY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjYyIsInByZXZpb3VzX3JlY2VpcHRfaWQiOiIxOTE5OTQ3YWY2NzU5YzJiMTJkMTU3ODNkYTY3Y2ZjNjhlYjAxMTU0OWI2MGU5NTU0MmUwZjkyZGU2ZGE4MzljIiwicHJldmlvdXNfcmVjZWlwdF9zaGEyNTYiOiIwYjljNDE4NTlhMDk3YTU4ZDg0Mjg5MjM2MWMzOWM3YzhmOGQ5Y2ZhZmEzNzg2NjYxNjBjNTllMTBhNmFiOWY2IiwicHJvamVjdF9kb21haW5faWQiOiJtYXRyaXguYzIiLCJyZWNlaXB0X2lkIjoiOGE3YzY5YTk3NzFjNTQwOTJjMjYzM2ExNTU1NDRkZTA2NDAyMTk0OGEyNWEwNWNkZDJjMzEyOGRkOWNmZjhhMCIsInJlY2VpcHRfcHJvdG9jb2xfdmVyc2lvbiI6MSwicmVjZWlwdF90eXBlIjoiUk9PVF9QUkVQQVJFRCIsInJvb3Rfc2VxdWVuY2UiOjQsInJvb3Rfc3RvcmVfaWQiOiIxMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExIiwicnVuX2lkIjoiNDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCIsInNpZ25hdHVyZV9iNjQiOiI2b1grVkFRR1BzV1JZSU9wK05GcTVCUFRyRkQvbGFTMm5mWlNhYkdHQmprNEZpVGV2YWtiMm1BR3ppcXhrOGY5QnhFUmpBamMrK3EyU3lpMUVmMUJBdz09Iiwic2lnbmVyX2tleV9pZCI6ImVkMjU1MTk6NWIxMzMxZDJlMmJmMGNhY2RmZGEwNmE1NDU2OWE3MTZkY2U2MjYzMWJhMzc1Mzk3ZWFhYTZlYTU2YjM1YmIyNyIsInNwb3J0X2lkIjoiZm9vdGJhbGwifQo=",
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiJkNzI0ZWIxNGIzNzg1NmMzMDM1NjlhMGQyMDQ4NmY2Nzk5MDA4OTVkMmEzYWQ4ODQzOTE3MmJlYWVkMGVkMjIwIiwiY29udHJvbF9pZCI6IjMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMiLCJjcmVhdGVkX2F0IjoiMjAyNi0wOC0yNVQyMzowMDowNCswMDowMCIsImRhdGFiYXNlX2luc3RhbmNlX2lkIjoiMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMiIsImRvbWFpbl9zZXBhcmF0b3IiOiJtYXRyaXguYzItcjgtM3I2LWV4dGVybmFsLWludGVncml0eS1yb290LzEiLCJsb2NhbF9jb250cm9sX3N0YXRlX3ZlcnNpb24iOm51bGwsImxvY2FsX3NjaGVtYV91c2VyX3ZlcnNpb24iOjg3LCJsb2NhbF90cmFuc2l0aW9uX2V2ZW50X2lkIjpudWxsLCJsb2NhbF90cmFuc2l0aW9uX2V2ZW50X3NoYTI1NiI6bnVsbCwibG9jYWxfdHJhbnNpdGlvbl9zZXF1ZW5jZSI6bnVsbCwibWV0YWRhdGEiOnsicHJlcGFyZWRfcmVjZWlwdF9pZCI6IjhhN2M2OWE5NzcxYzU0MDkyYzI2MzNhMTU1NTQ0ZGUwNjQwMjE5NDhhMjVhMDVjZGQyYzMxMjhkZDljZmY4YTAiLCJwcmVwYXJlZF9yZWNlaXB0X3NoYTI1NiI6IjVkN2U5ZjQ5YmY1MmE2MjEyYzhhOGE2ZmUxZTk1Y2IwN2Y1ODU3NWQwOTEwNWU2MjdmM2UwMDVjNmE2NTVhNzAifSwib3BlcmF0aW9uX2lkIjoiY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjYyIsInByZXZpb3VzX3JlY2VpcHRfaWQiOiI4YTdjNjlhOTc3MWM1NDA5MmMyNjMzYTE1NTU0NGRlMDY0MDIxOTQ4YTI1YTA1Y2RkMmMzMTI4ZGQ5Y2ZmOGEwIiwicHJldmlvdXNfcmVjZWlwdF9zaGEyNTYiOiI1ZDdlOWY0OWJmNTJhNjIxMmM4YThhNmZlMWU5NWNiMDdmNTg1NzVkMDkxMDVlNjI3ZjNlMDA1YzZhNjU1YTcwIiwicHJvamVjdF9kb21haW5faWQiOiJtYXRyaXguYzIiLCJyZWNlaXB0X2lkIjoiMmZhNDU0NDAxZGFmNmU0ZjkwYmJhODczNjk1MmQ0Mzg0MzZmZTY3MDhkYTVlOGQwYWVlZDhkYTJkNzlmMDJiNCIsInJlY2VpcHRfcHJvdG9jb2xfdmVyc2lvbiI6MSwicmVjZWlwdF90eXBlIjoiUk9PVF9BQk9SVEVEIiwicm9vdF9zZXF1ZW5jZSI6NSwicm9vdF9zdG9yZV9pZCI6IjExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEiLCJydW5faWQiOiI0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0Iiwic2lnbmF0dXJlX2I2NCI6IjBtSEN4blNSZlIvNmVYdmhyMldRdUMvc1BPbDVRbTQ3VW95Y2hqT3hiQXViVldTRlNyczhCV0pEMjlEZysrTW5lVHdOSG92b2xKTGN6Ukd6M3Q4ckRnPT0iLCJzaWduZXJfa2V5X2lkIjoiZWQyNTUxOTo1YjEzMzFkMmUyYmYwY2FjZGZkYTA2YTU0NTY5YTcxNmRjZTYyNjMxYmEzNzUzOTdlYWFhNmVhNTZiMzViYjI3Iiwic3BvcnRfaWQiOiJmb290YmFsbCJ9Cg==",
    "eyJjYW5vbmljYWxfcGF5bG9hZF9zaGEyNTYiOiIzM2FkMjU5M2NlZjkxZmY2MzY3M2Q2YTgxYmUwZGMxYTQyYTcwNzRlYTlmMzdlNmQzNzI0OTgwZTlmMjY1ZGM2IiwiY29udHJvbF9pZCI6bnVsbCwiY3JlYXRlZF9hdCI6IjIwMjYtMDgtMjVUMjM6MDA6MDUrMDA6MDAiLCJkYXRhYmFzZV9pbnN0YW5jZV9pZCI6IjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIiLCJkb21haW5fc2VwYXJhdG9yIjoibWF0cml4LmMyLXI4LTNyNi1leHRlcm5hbC1pbnRlZ3JpdHktcm9vdC8xIiwibG9jYWxfY29udHJvbF9zdGF0ZV92ZXJzaW9uIjpudWxsLCJsb2NhbF9zY2hlbWFfdXNlcl92ZXJzaW9uIjo4NywibG9jYWxfdHJhbnNpdGlvbl9ldmVudF9pZCI6bnVsbCwibG9jYWxfdHJhbnNpdGlvbl9ldmVudF9zaGEyNTYiOm51bGwsImxvY2FsX3RyYW5zaXRpb25fc2VxdWVuY2UiOm51bGwsIm1ldGFkYXRhIjp7ImFjdGl2YXRpb25fc2VxdWVuY2UiOjcsIm5ld19rZXlfaWQiOiJlZDI1NTE5OmViODI5MTk2Nzc3ZDA2YzFiYzcyZTA3OTA2ZDMyZWQ3MGU2MWRmOTYwMWU4ZTI3OTA1NWNhYTJjYzY1YjU3NTIiLCJuZXdfa2V5X3Byb29mX3NpZ25hdHVyZV9iNjQiOiJvZ2VBblhNZGJDV1F6RnU4M1JNQ0VHdVdJR01vemM4eGo3WEFEbkVDSUN6cHZWL0k1YnZ6QjhHVVEzTFI2OWpDemlIWGFXYUhOTkFwRG9RcDhocklEUT09IiwibmV3X3B1YmxpY19rZXlfYjY0IjoiNHhhU0Nvay9LWWxNYythdXRWM0JaMHl3M0RZVVhDc2tQQWJlWHdBZG9oaz0iLCJuZXdfcHVibGljX2tleV9maW5nZXJwcmludCI6ImViODI5MTk2Nzc3ZDA2YzFiYzcyZTA3OTA2ZDMyZWQ3MGU2MWRmOTYwMWU4ZTI3OTA1NWNhYTJjYzY1YjU3NTIiLCJwcm9vZl9jb3JlIjp7ImFjdGl2YXRpb25fc2VxdWVuY2UiOjcsImRhdGFiYXNlX2luc3RhbmNlX2lkIjoiMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMiIsIm5ld19rZXlfaWQiOiJlZDI1NTE5OmViODI5MTk2Nzc3ZDA2YzFiYzcyZTA3OTA2ZDMyZWQ3MGU2MWRmOTYwMWU4ZTI3OTA1NWNhYTJjYzY1YjU3NTIiLCJvcGVyYXRpb25faWQiOiJkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkIiwicm9vdF9zdG9yZV9pZCI6IjExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEiLCJzY2hlbWEiOiJtYXRyaXguYzItcjgtM3I2LWtleS1yb3RhdGlvbi1wcm9vZi1jb3JlLzEifX0sIm9wZXJhdGlvbl9pZCI6ImRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGRkZGQiLCJwcmV2aW91c19yZWNlaXB0X2lkIjoiMmZhNDU0NDAxZGFmNmU0ZjkwYmJhODczNjk1MmQ0Mzg0MzZmZTY3MDhkYTVlOGQwYWVlZDhkYTJkNzlmMDJiNCIsInByZXZpb3VzX3JlY2VpcHRfc2hhMjU2IjoiNjkwM2IwNWRlNjVkMzdjNjBkM2I3Nzc3ZjM0MDFjNjNjMGFmM2MzM2QyYzY5NDI3ZDM5MzZhOTc5YTBmNTM5YyIsInByb2plY3RfZG9tYWluX2lkIjoibWF0cml4LmMyIiwicmVjZWlwdF9pZCI6ImZjMDM0N2YxN2E2NjdjYTYzMmMzNDljZWQ3NTA0YTAwZmFkZTQ3Y2E1ZDg5MjAzNzE0MmM0NTI5ZjQzODc5ZWYiLCJyZWNlaXB0X3Byb3RvY29sX3ZlcnNpb24iOjEsInJlY2VpcHRfdHlwZSI6IlJPT1RfS0VZX1JPVEFUSU9OIiwicm9vdF9zZXF1ZW5jZSI6Niwicm9vdF9zdG9yZV9pZCI6IjExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEiLCJydW5faWQiOm51bGwsInNpZ25hdHVyZV9iNjQiOiJNaXl3SHpXUkl1d2ZFZlovR0s0RVVQR1hXTmN1U2d1dGFrZ2x2Q3BhQjJvOGdXbm1kMzE0QXpTTjhIQ1NVVEpiS3hqWmNsSWMxL2dvdzY3V3JNdkpDdz09Iiwic2lnbmVyX2tleV9pZCI6ImVkMjU1MTk6NWIxMzMxZDJlMmJmMGNhY2RmZGEwNmE1NDU2OWE3MTZkY2U2MjYzMWJhMzc1Mzk3ZWFhYTZlYTU2YjM1YmIyNyIsInNwb3J0X2lkIjoiZm9vdGJhbGwifQo="
]
PARITY_OLD_DER_B64 = 'MCowBQYDK2VwAyEA+e8s72xeWMqWbXOVYJdnSg6eBCkIfcXdJGymcDN074I='
PARITY_OLD_RAW_B64 = '+e8s72xeWMqWbXOVYJdnSg6eBCkIfcXdJGymcDN074I='
PARITY_OLD_FP = '5b1331d2e2bf0cacdfda06a54569a716dce62631ba375397eaaa6ea56b35bb27'
PARITY_OLD_KEY_ID = 'ed25519:5b1331d2e2bf0cacdfda06a54569a716dce62631ba375397eaaa6ea56b35bb27'

ROOT_ID = "1" * 64
DB_ID = "2" * 64
CONTROL_ID = "3" * 64
RUN_ID = "4" * 64
EVENT1_ID = "5" * 64
EVENT1_SHA = "6" * 64
EVENT2_ID = "7" * 64
EVENT2_SHA = "8" * 64
SIGNING_ACCOUNT = "111111111111"
ARCHIVE_ACCOUNT = "222222222222"
REGION = "us-east-1"
KMS_ARN = f"arn:aws:kms:{REGION}:{SIGNING_ACCOUNT}:key/abcd-1234"
BUCKET = "matrix-r836-authority-test"
ROLE = "MatrixArchiveAppend"
INVOKED_ARN = f"arn:aws:lambda:{REGION}:{SIGNING_ACCOUNT}:function:matrix-r836-authority:governed"


class FakeAwsError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__("FAKE_AWS_ERROR_WITH_SECRET_TEXT")
        self.response = {
            "ResponseMetadata": {"HTTPStatusCode": status},
            "Error": {"Code": code, "Message": "FAKE_SECRET_MESSAGE"},
        }


class FakeKms:
    def __init__(self, private: Ed25519PrivateKey, *, call_order=None) -> None:
        self.private = private
        self.call_order = [] if call_order is None else call_order
        self.calls = []
        self.bad_signature = False
        self.describe_override = None
        self.public_override = None
        self.sign_override = None
        self.der = private.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.raw = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    def describe_key(self, **kwargs):
        self.call_order.append("kms:DescribeKey")
        self.calls.append(("describe_key", kwargs))
        if isinstance(self.describe_override, Exception):
            raise self.describe_override
        if self.describe_override is not None:
            return self.describe_override
        return {
            "KeyMetadata": {
                "Arn": KMS_ARN,
                "KeyId": KMS_ARN.split("/")[-1],
                "KeySpec": "ECC_NIST_EDWARDS25519",
                "KeyUsage": "SIGN_VERIFY",
                "KeyState": "Enabled",
            }
        }

    def get_public_key(self, **kwargs):
        self.call_order.append("kms:GetPublicKey")
        self.calls.append(("get_public_key", kwargs))
        if isinstance(self.public_override, Exception):
            raise self.public_override
        if self.public_override is not None:
            return self.public_override
        return {
            "KeyId": KMS_ARN.split("/")[-1],
            "KeySpec": "ECC_NIST_EDWARDS25519",
            "KeyUsage": "SIGN_VERIFY",
            "SigningAlgorithms": ["ED25519_SHA_512"],
            "PublicKey": self.der,
        }

    def sign(self, **kwargs):
        self.call_order.append("kms:Sign")
        self.calls.append(("sign", kwargs))
        if isinstance(self.sign_override, Exception):
            raise self.sign_override
        if self.sign_override is not None:
            return self.sign_override
        signature = self.private.sign(kwargs["Message"])
        if self.bad_signature:
            signature = b"x" * 64
        return {
            "KeyId": KMS_ARN.split("/")[-1],
            "SigningAlgorithm": "ED25519_SHA_512",
            "Signature": signature,
        }


class FakeSts:
    def __init__(self, *, call_order=None) -> None:
        self.call_order = [] if call_order is None else call_order
        self.calls = []
        self.wrong_identity = False
        self.error = None

    def assume_role(self, **kwargs):
        self.call_order.append("sts:AssumeRole")
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        session = kwargs["RoleSessionName"]
        account = "999999999999" if self.wrong_identity else ARCHIVE_ACCOUNT
        return {
            "AssumedRoleUser": {
                "Arn": f"arn:aws:sts::{account}:assumed-role/{ROLE}/{session}"
            },
            "Credentials": {
                "AccessKeyId": "FAKE_ACCESS",
                "SecretAccessKey": "FAKE_SECRET",
                "SessionToken": "FAKE_SESSION",
            },
        }


class FakeS3:
    def __init__(self, *, call_order=None) -> None:
        self.call_order = [] if call_order is None else call_order
        self.objects = {}
        self.calls = []
        self.put_faults = []
        self.get_faults = []
        self.list_faults = []
        self.page_size = 1000
        self.force_content_length = None
        self.race_body = None

    def list_objects_v2(self, **kwargs):
        self.call_order.append("s3:ListObjectsV2")
        self.calls.append(("list_objects_v2", kwargs))
        if self.list_faults:
            fault = self.list_faults.pop(0)
            if fault is not None:
                raise fault
        prefix = kwargs["Prefix"]
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        start = int(kwargs.get("ContinuationToken", "0"))
        page = keys[start:start + self.page_size]
        next_index = start + len(page)
        truncated = next_index < len(keys)
        response = {
            "Contents": [{"Key": key} for key in page],
            "IsTruncated": truncated,
        }
        if truncated:
            response["NextContinuationToken"] = str(next_index)
        return response

    def get_object(self, **kwargs):
        self.call_order.append("s3:GetObject")
        self.calls.append(("get_object", kwargs))
        if self.get_faults:
            fault = self.get_faults.pop(0)
            if fault is not None:
                raise fault
        key = kwargs["Key"]
        if key not in self.objects:
            raise FakeAwsError(404, "NoSuchKey")
        raw = self.objects[key]
        length = len(raw) if self.force_content_length is None else self.force_content_length
        return {"Body": raw, "ContentLength": length}

    def put_object(self, **kwargs):
        self.call_order.append("s3:PutObject")
        self.calls.append(("put_object", kwargs))
        if self.put_faults:
            fault = self.put_faults.pop(0)
            if fault == "timeout_after_write":
                self.objects[kwargs["Key"]] = kwargs["Body"]
                raise TimeoutError("FAKE_TIMEOUT_SECRET")
            if fault == "timeout_before_write":
                raise TimeoutError("FAKE_TIMEOUT_SECRET")
            if fault == "500_after_write":
                self.objects[kwargs["Key"]] = kwargs["Body"]
                raise FakeAwsError(500, "InternalError")
            if fault == "412_after_write":
                self.objects[kwargs["Key"]] = kwargs["Body"]
                raise FakeAwsError(412, "PreconditionFailed")
            if fault == "409_after_write":
                self.objects[kwargs["Key"]] = kwargs["Body"]
                raise FakeAwsError(409, "ConditionalRequestConflict")
            if fault == "tamper_after_write":
                self.objects[kwargs["Key"]] = b"{}"
                return {"ETag": "tampered"}
            if fault == "412_with_race_body":
                assert isinstance(self.race_body, bytes)
                self.objects[kwargs["Key"]] = self.race_body
                raise FakeAwsError(412, "PreconditionFailed")
            if isinstance(fault, Exception):
                raise fault
        if kwargs["Key"] in self.objects:
            raise FakeAwsError(412, "PreconditionFailed")
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {"ETag": "fake"}


class Clock:
    def __init__(self, start=None):
        self.value = start or datetime(2026, 8, 25, 23, 0, tzinfo=UTC)

    def __call__(self):
        current = self.value
        self.value = current + timedelta(seconds=1)
        return current


def config(**changes):
    values = dict(
        root_store_id=ROOT_ID,
        database_instance_id=DB_ID,
        archive_account_id=ARCHIVE_ACCOUNT,
        archive_region=REGION,
        archive_bucket=BUCKET,
        archive_append_role_name=ROLE,
        signing_key_arn=KMS_ARN,
        key_epoch=1,
        authority_code_sha256="a" * 64,
    )
    values.update(changes)
    return auth.AuthorityConfig(**values)


def invocation(*, arn=INVOKED_ARN, remaining=30000):
    return auth.InvocationMetadata(arn, lambda: remaining)


def make_runtime(*, private=None, s3=None, kms=None, sts=None, clock=None, max_attempts=3, call_order=None):
    if private is None:
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"matrix-r836-test-key").digest())
    order = [] if call_order is None else call_order
    kms = kms or FakeKms(private, call_order=order)
    sts = sts or FakeSts(call_order=order)
    s3 = s3 or FakeS3(call_order=order)
    clock = clock or Clock()
    service = auth.AuthorityService(
        config=config(),
        kms_client=kms,
        sts_client=sts,
        s3_client_factory=lambda credentials, region: s3,
        clock=clock,
        sleeper=lambda attempt: None,
        max_attempts=max_attempts,
    )
    return service, private, kms, sts, s3, order


def common(operation, nonce="req-1"):
    return {
        "schema": auth.REQUEST_SCHEMA,
        "operation": operation,
        "request_nonce": nonce,
        "root_store_id": ROOT_ID,
        "database_instance_id": DB_ID,
    }


def genesis_request(*, nonce="genesis-1", operation_id="a" * 64):
    event = common("APPEND_RECEIPT", nonce)
    event["expected_head"] = {"sequence": 0, "receipt_id": None, "receipt_sha256": None}
    event["receipt_intent"] = {
        "receipt_type": "ROOT_GENESIS",
        "operation_id": operation_id,
        "control_id": None,
        "run_id": None,
        "local_transition_event_id": None,
        "local_transition_event_sha256": None,
        "local_transition_sequence": None,
        "local_control_state_version": None,
        "local_schema_user_version": 87,
        "metadata": {
            "local_snapshot_sha256": "b" * 64,
            "genesis_transition_events": [],
            "genesis_run_state": [],
        },
    }
    return event


def expected_head_from(response):
    return dict(response["head"])


def prepared_request(head, *, nonce="prepare-1", operation_id="b" * 64, outcome="STATE_TRANSITION_COMMITTED"):
    event = common("APPEND_RECEIPT", nonce)
    event["expected_head"] = dict(head)
    before = 0
    after = 1 if outcome == "STATE_TRANSITION_COMMITTED" else 0
    event["receipt_intent"] = {
        "receipt_type": "ROOT_PREPARED",
        "operation_id": operation_id,
        "control_id": CONTROL_ID,
        "run_id": RUN_ID,
        "local_transition_event_id": EVENT1_ID,
        "local_transition_event_sha256": EVENT1_SHA,
        "local_transition_sequence": 1,
        "local_control_state_version": after,
        "local_schema_user_version": 87,
        "metadata": {
            "expected_outcome": outcome,
            "expected_prior_state": "PLANNED",
            "expected_next_state": "IN_PROGRESS",
            "expected_state_version_before": before,
            "expected_state_version_after": after,
        },
    }
    return event


def committed_request(head, prepared_response, *, nonce="commit-1", operation_id="b" * 64):
    event = common("APPEND_RECEIPT", nonce)
    event["expected_head"] = dict(head)
    event["receipt_intent"] = {
        "receipt_type": "ROOT_COMMITTED",
        "operation_id": operation_id,
        "control_id": CONTROL_ID,
        "run_id": RUN_ID,
        "local_transition_event_id": EVENT1_ID,
        "local_transition_event_sha256": EVENT1_SHA,
        "local_transition_sequence": 1,
        "local_control_state_version": 1,
        "local_schema_user_version": 87,
        "metadata": {
            "prepared_receipt_id": prepared_response["receipt"]["receipt_id"],
            "prepared_receipt_sha256": prepared_response["receipt"]["receipt_sha256"],
        },
    }
    return event


def aborted_request(head, prepared_response, *, nonce="abort-1", operation_id="c" * 64):
    event = common("APPEND_RECEIPT", nonce)
    event["expected_head"] = dict(head)
    event["receipt_intent"] = {
        "receipt_type": "ROOT_ABORTED",
        "operation_id": operation_id,
        "control_id": CONTROL_ID,
        "run_id": RUN_ID,
        "local_transition_event_id": None,
        "local_transition_event_sha256": None,
        "local_transition_sequence": None,
        "local_control_state_version": None,
        "local_schema_user_version": 87,
        "metadata": {
            "prepared_receipt_id": prepared_response["receipt"]["receipt_id"],
            "prepared_receipt_sha256": prepared_response["receipt"]["receipt_sha256"],
        },
    }
    return event


def append_genesis(runtime=None):
    if runtime is None:
        runtime = make_runtime()
    service, private, kms, sts, s3, order = runtime
    response = service.handle(genesis_request(), invocation=invocation())
    assert response["status"] == "APPENDED"
    return runtime, response


def load_parity_chain(s3):
    prefix = config().receipt_prefix
    for raw_b64 in PARITY_RECEIPTS_B64:
        raw = base64.b64decode(raw_b64)
        receipt = auth.AuthorityReceipt.from_bytes(raw)
        s3.objects[f"{prefix}{receipt.root_sequence:020d}.json"] = raw


def expect_code(code, func):
    with pytest.raises(auth.AuthorityError, match=code):
        func()


def source_text():
    return SOURCE_PATH.read_text(encoding="utf-8")


def requirements_text():
    return REQUIREMENTS_PATH.read_text(encoding="utf-8")


def design_text():
    return DESIGN_PATH.read_text(encoding="utf-8")


def impl_doc_text():
    return IMPL_DOC_PATH.read_text(encoding="utf-8")


def static_no_top_level_boto_import():
    tree = ast.parse(source_text())
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"boto3", "botocore"} for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {"boto3", "botocore", "botocore.config"}


def parity_receipts():
    return [auth.AuthorityReceipt.from_bytes(base64.b64decode(x)) for x in PARITY_RECEIPTS_B64]


def _fresh_append_for_fault(fault):
    runtime, genesis = append_genesis()
    service, private, kms, sts, s3, order = runtime
    event = prepared_request(genesis["head"])
    s3.put_faults.append(fault)
    return runtime, event

def _assert_asd(asd):
    if asd == "ASD01":
        assert "def handler(event: Any, context: Any)" in source_text()
        assert "authority_service.handler" in design_text()
    elif asd == "ASD02":
        assert "class AuthorityService:" in source_text()
        assert "def handler(" in source_text()
    elif asd == "ASD03":
        text = source_text()
        for token in ("kms_client", "sts_client", "s3_client_factory", "clock", "sleeper"):
            assert token in text
    elif asd == "ASD04":
        static_no_top_level_boto_import()
        assert "def build_real_service(" in source_text()
    elif asd == "ASD05":
        event = common("READ_HEAD")
        event["unknown"] = 1
        expect_code("REQUEST_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD06":
        event = common("GENERIC_KMS_PROXY")
        expect_code("OPERATION_UNSUPPORTED", lambda: auth.parse_request(event, config()))
        assert {"APPEND_RECEIPT", "READ_HEAD", "READ_RECEIPT"} == {
            "APPEND_RECEIPT", "READ_HEAD", "READ_RECEIPT"
        }
    elif asd == "ASD07":
        assert 'operation == "APPEND_RECEIPT"' in source_text()
        assert "GENERIC_S3" not in source_text()
    elif asd == "ASD08":
        service, private, kms, sts, s3, order = make_runtime()
        response = service.handle(common("READ_HEAD"), invocation=invocation())
        assert response["status"] == "HEAD"
        assert not [x for x in kms.calls if x[0] == "sign"]
        assert not [x for x in s3.calls if x[0] == "put_object"]
    elif asd == "ASD09":
        event = common("READ_RECEIPT")
        event["sequence"] = 0
        expect_code("READ_SEQUENCE_INVALID", lambda: auth.parse_request(event, config()))
    elif asd == "ASD10":
        event = common("READ_HEAD", nonce="bad nonce with spaces")
        expect_code("REQUEST_NONCE_INVALID", lambda: auth.parse_request(event, config()))
    elif asd == "ASD11":
        event = common("READ_HEAD")
        event["root_store_id"] = "f" * 64
        expect_code("REQUEST_ROOT_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD12":
        values = config().__dict__.copy()
        values["project_domain_id"] = "other"
        expect_code("CONFIG_PROJECT_MISMATCH", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD13":
        values = config().__dict__.copy()
        values["sport_id"] = "tennis"
        expect_code("CONFIG_SPORT_MISMATCH", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD14":
        values = config().__dict__.copy()
        values["authority_profile"] = "WEAK"
        expect_code("CONFIG_PROFILE_MISMATCH", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD15":
        values = config().__dict__.copy()
        values["root_store_id"] = "x"
        expect_code("CONFIG_ROOT_INVALID", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD16":
        values = config().__dict__.copy()
        values["database_instance_id"] = "x"
        expect_code("CONFIG_DATABASE_INVALID", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD17":
        event = common("READ_HEAD")
        event["archive_bucket"] = "attacker"
        expect_code("REQUEST_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD18":
        event = common("READ_HEAD")
        event["kms_key_arn"] = KMS_ARN
        expect_code("REQUEST_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD19":
        expect_code(
            "GOVERNED_ALIAS_REQUIRED",
            lambda: invocation(arn=INVOKED_ARN.rsplit(":", 1)[0] + ":$LATEST").validate_for(config()),
        )
    elif asd == "ASD20":
        invocation().validate_for(config())
        assert auth.GOVERNED_ALIAS == "governed"
    elif asd == "ASD21":
        wrong_region = f"arn:aws:lambda:eu-west-1:{SIGNING_ACCOUNT}:function:x:governed"
        expect_code("SIGNING_REGION_MISMATCH", lambda: invocation(arn=wrong_region).validate_for(config()))
        wrong_account = f"arn:aws:lambda:{REGION}:999999999999:function:x:governed"
        expect_code("SIGNING_ACCOUNT_MISMATCH", lambda: invocation(arn=wrong_account).validate_for(config()))
    elif asd == "ASD22":
        service, private, kms, sts, s3, order = make_runtime()
        service.handle(common("READ_HEAD"), invocation=invocation())
        assert sts.calls[0]["RoleArn"] == f"arn:aws:iam::{ARCHIVE_ACCOUNT}:role/{ROLE}"
    elif asd == "ASD23":
        sts = FakeSts()
        sts.wrong_identity = True
        service, *_ = make_runtime(sts=sts)
        expect_code("STS_ASSUMED_ROLE_IDENTITY_MISMATCH", lambda: service.handle(common("READ_HEAD"), invocation=invocation()))
    elif asd == "ASD24":
        doc = design_text()
        assert "raw `kms:Sign`" in doc
        assert "direct S3 receipt write" in doc
        assert "receipt delete" in doc
    elif asd == "ASD25":
        event = genesis_request()
        event["receipt_intent"]["aws_secret_access_key"] = "secret"
        expect_code("RECEIPT_INTENT_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD26":
        text = source_text()
        assert 'os.environ["AWS_ACCESS_KEY_ID"]' not in text
        assert 'os.environ.get("AWS_ACCESS_KEY_ID")' not in text
        assert "credential/environment dump" not in text.lower()
    elif asd == "ASD27":
        assert "print(event" not in source_text()
        assert "json.dumps(event" not in source_text()
    elif asd == "ASD28":
        error = auth.AuthorityError("R8_3R6_AUTH_TEST_CODE")
        assert str(error) == "R8_3R6_AUTH_TEST_CODE"
    elif asd == "ASD29":
        original = auth.build_real_service
        auth.build_real_service = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("VERY_SECRET_EXCEPTION"))
        stream = io.StringIO()
        try:
            with redirect_stdout(stream):
                response = auth.handler({"request_nonce": "safe-1"}, type("C", (), {
                    "invoked_function_arn": INVOKED_ARN,
                    "get_remaining_time_in_millis": lambda self: 30000,
                })())
        finally:
            auth.build_real_service = original
        assert response["error_code"] == "R8_3R6_AUTH_UNEXPECTED_FAIL_CLOSED"
        assert "VERY_SECRET_EXCEPTION" not in stream.getvalue()
        assert "VERY_SECRET_EXCEPTION" not in json.dumps(response)
    elif asd == "ASD30":
        event = common("READ_HEAD", nonce="x" * 70000)
        expect_code("REQUEST_TOO_LARGE", lambda: auth.parse_request(event, config()))
    elif asd == "ASD31":
        head = auth._parse_expected_head({"sequence": 0, "receipt_id": None, "receipt_sha256": None})
        assert head == auth.AuthorityHead(0, None, None)
        expect_code("EXPECTED_GENESIS_HEAD_INVALID", lambda: auth._parse_expected_head({"sequence": 0, "receipt_id": "a"*64, "receipt_sha256": None}))
    elif asd == "ASD32":
        runtime, response = append_genesis()
        assert response["receipt"]["root_sequence"] == 1
    elif asd == "ASD33":
        cfg = config()
        assert cfg.receipt_key(1).endswith("/receipts/00000000000000000001.json")
        assert CONTROL_ID not in cfg.receipt_prefix and RUN_ID not in cfg.receipt_prefix
    elif asd == "ASD34":
        runtime, response = append_genesis()
        raw = next(iter(runtime[4].objects.values()))
        receipt = auth.AuthorityReceipt.from_bytes(raw)
        assert receipt.root_sequence == 1 and receipt.previous_receipt_id is None
        assert receipt.receipt_type == "ROOT_GENESIS"
    elif asd == "ASD35":
        assert auth.RECEIPT_TYPES == (
            "ROOT_GENESIS", "ROOT_PREPARED", "ROOT_COMMITTED", "ROOT_ABORTED", "ROOT_KEY_ROTATION"
        )
    elif asd == "ASD36":
        event = genesis_request()
        event["receipt_intent"]["receipt_type"] = "ROOT_KEY_ROTATION"
        expect_code("KEY_ROTATION_NOT_GOVERNED", lambda: auth.parse_request(event, config()))
    elif asd == "ASD37":
        runtime, response = append_genesis()
        receipt = auth.AuthorityReceipt.from_bytes(next(iter(runtime[4].objects.values())))
        assert set(receipt.metadata) == {
            "backend_profile", "controlled_live_admissible", "local_snapshot_sha256",
            "genesis_transition_events", "genesis_run_state", "bootstrap_public_key_b64",
            "bootstrap_public_key_fingerprint", "bootstrap_signer_key_id",
        }
        assert receipt.metadata["backend_profile"] == auth.AUTHORITY_PROFILE
        assert receipt.metadata["controlled_live_admissible"] is False
        assert receipt.metadata["bootstrap_signer_key_id"] == receipt.signer_key_id
    elif asd == "ASD38":
        event = prepared_request({"sequence": 1, "receipt_id": "a"*64, "receipt_sha256": "b"*64})
        parsed = auth.parse_request(event, config())
        assert set(parsed.receipt_intent["metadata"]) == {
            "expected_outcome", "expected_prior_state", "expected_next_state",
            "expected_state_version_before", "expected_state_version_after",
        }
    elif asd == "ASD39":
        runtime, genesis = append_genesis()
        service = runtime[0]
        prepared = service.handle(prepared_request(genesis["head"]), invocation=invocation())
        committed = service.handle(committed_request(prepared["head"], prepared), invocation=invocation())
        assert committed["status"] == "APPENDED"
        assert committed["receipt"]["receipt_type"] == "ROOT_COMMITTED"
    elif asd == "ASD40":
        runtime, genesis = append_genesis()
        service = runtime[0]
        prepared_event = prepared_request(genesis["head"], operation_id="c"*64, outcome="STATE_TRANSITION_FAILED")
        prepared = service.handle(prepared_event, invocation=invocation())
        aborted = service.handle(aborted_request(prepared["head"], prepared), invocation=invocation())
        assert aborted["receipt"]["receipt_type"] == "ROOT_ABORTED"
        receipt = auth.AuthorityReceipt.from_bytes(runtime[4].objects[config().receipt_key(3)])
        assert receipt.local_transition_event_id is None
    elif asd == "ASD41":
        assert "R8_3R6_AUTH_KEY_ROTATION_NOT_GOVERNED" in source_text()
        assert "KEY_ROTATION_RUNTIME_ENABLEMENT=FALSE" in impl_doc_text()
    elif asd == "ASD42":
        assert "CloudFormation replacement" in design_text()
        assert "never" in design_text()[design_text().find("CloudFormation replacement"):design_text().find("CloudFormation replacement")+120]
    elif asd == "ASD43":
        event = prepared_request({"sequence": 1, "receipt_id": "a"*64, "receipt_sha256": "b"*64})
        event["receipt_intent"]["metadata"]["hidden"] = 1
        expect_code("PREPARED_METADATA_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD44":
        event = genesis_request()
        event["receipt_intent"]["signer_key_id"] = "ed25519:" + "a"*64
        expect_code("RECEIPT_INTENT_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif asd == "ASD45":
        runtime, response = append_genesis()
        kms = runtime[2]
        assert [name for name, _ in kms.calls[:2]] == ["describe_key", "get_public_key"]
        assert kms.calls[0][1]["KeyId"] == KMS_ARN
    elif asd == "ASD46":
        der = base64.b64decode(PARITY_OLD_DER_B64)
        public = serialization.load_der_public_key(der)
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        assert base64.b64encode(raw).decode("ascii") == PARITY_OLD_RAW_B64
        assert hashlib.sha256(raw).hexdigest() == PARITY_OLD_FP
    elif asd == "ASD47":
        assert PARITY_OLD_KEY_ID == "ed25519:" + PARITY_OLD_FP
        runtime, response = append_genesis()
        receipt = auth.AuthorityReceipt.from_bytes(next(iter(runtime[4].objects.values())))
        assert receipt.signer_key_id.startswith("ed25519:")
    elif asd == "ASD48":
        runtime, response = append_genesis()
        sign_call = [kwargs for name, kwargs in runtime[2].calls if name == "sign"][0]
        assert sign_call["KeyId"] == KMS_ARN
        assert sign_call["MessageType"] == "RAW"
        assert sign_call["SigningAlgorithm"] == "ED25519_SHA_512"
    elif asd == "ASD49":
        runtime, response = append_genesis()
        sign_call = [kwargs for name, kwargs in runtime[2].calls if name == "sign"][0]
        message = sign_call["Message"]
        assert message.endswith(b"\n")
        assert hashlib.sha256(message).hexdigest() == response["receipt"]["canonical_payload_sha256"]
    elif asd == "ASD50":
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"bad-signature").digest())
        kms = FakeKms(private)
        kms.bad_signature = True
        service, private, kms, sts, s3, order = make_runtime(private=private, kms=kms)
        expect_code("KMS_SIGNATURE_VERIFICATION_FAILED", lambda: service.handle(genesis_request(), invocation=invocation()))
        assert not [x for x in s3.calls if x[0] == "put_object"]
    elif asd == "ASD51":
        runtime, response = append_genesis()
        receipt = auth.AuthorityReceipt.from_bytes(next(iter(runtime[4].objects.values())))
        assert receipt.canonical_payload_sha256 == hashlib.sha256(auth._canonical_bytes(receipt.unsigned_payload())).hexdigest()
    elif asd == "ASD52":
        runtime, response = append_genesis()
        receipt = auth.AuthorityReceipt.from_bytes(next(iter(runtime[4].objects.values())))
        expected = auth._sha({
            "schema": auth.RECEIPT_ID_SCHEMA,
            "canonical_payload_sha256": receipt.canonical_payload_sha256,
            "signature_b64": receipt.signature_b64,
        })
        assert receipt.receipt_id == expected
    elif asd == "ASD53":
        receipts = parity_receipts()
        for receipt, encoded in zip(receipts, PARITY_RECEIPTS_B64):
            assert receipt.canonical_bytes() == base64.b64decode(encoded)
        active, trusted = auth.verify_receipt_chain(receipts, expected_root_store_id=ROOT_ID, expected_database_instance_id=DB_ID)
        assert len(trusted) == 2 and active is not None
    elif asd == "ASD54":
        text = source_text()
        assert "Ed25519PrivateKey" not in text
        assert "ephemeral" not in text.lower()
    elif asd == "ASD55":
        order = []
        runtime = make_runtime(call_order=order)
        append_genesis(runtime)
        assert order.index("kms:DescribeKey") < order.index("sts:AssumeRole")
        assert order.index("kms:GetPublicKey") < order.index("sts:AssumeRole")
    elif asd == "ASD56":
        runtime, response = append_genesis()
        put = [kwargs for name, kwargs in runtime[4].calls if name == "put_object"][0]
        assert put["IfNoneMatch"] == "*"
        assert put["Bucket"] == BUCKET
        assert put["Key"] == config().receipt_key(1)
    elif asd == "ASD57":
        runtime, response = append_genesis()
        put = [kwargs for name, kwargs in runtime[4].calls if name == "put_object"][0]
        assert put["ContentType"] == "application/json"
        assert put["Body"] == runtime[4].objects[put["Key"]]
    elif asd == "ASD58":
        runtime, response = append_genesis()
        put = [kwargs for name, kwargs in runtime[4].calls if name == "put_object"][0]
        assert set(put["Metadata"]) == {
            "matrix-receipt-sha256", "matrix-receipt-id",
            "matrix-root-store-id", "matrix-database-instance-id",
        }
    elif asd == "ASD59":
        runtime, response = append_genesis()
        calls = [name for name, _ in runtime[4].calls]
        put_index = calls.index("put_object")
        assert "get_object" in calls[put_index + 1:]
    elif asd == "ASD60":
        runtime, event = _fresh_append_for_fault("412_after_write")
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "IDEMPOTENT_EXISTING"
    elif asd == "ASD61":
        runtime, event = _fresh_append_for_fault(FakeAwsError(409, "ConditionalRequestConflict"))
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "APPENDED"
        assert response["attempts"]["s3_put"] == 2
    elif asd == "ASD62":
        runtime, event = _fresh_append_for_fault("timeout_before_write")
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "APPENDED"
        assert response["reconciled"] is True
        calls = [name for name, _ in runtime[4].calls]
        first_put = calls.index("put_object")
        assert "get_object" in calls[first_put + 1:]
    elif asd == "ASD63":
        runtime, event = _fresh_append_for_fault("timeout_after_write")
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME"
        assert response["reconciled"] is True
    elif asd == "ASD64":
        runtime, event = _fresh_append_for_fault(FakeAwsError(403, "AccessDenied"))
        expect_code("AWS_AUTHORIZATION_FAILED", lambda: runtime[0].handle(event, invocation=invocation()))
        # one genesis put + one failing prepared put
        assert len([x for x in runtime[4].calls if x[0] == "put_object"]) == 2
    elif asd == "ASD65":
        runtime, event = _fresh_append_for_fault(FakeAwsError(500, "InternalError"))
        runtime[4].put_faults.extend([FakeAwsError(500, "InternalError"), FakeAwsError(500, "InternalError")])
        expect_code("S3_SERVICE_RETRY_EXHAUSTED", lambda: runtime[0].handle(event, invocation=invocation()))
        # one genesis put + three exhausted prepared attempts
        assert len([x for x in runtime[4].calls if x[0] == "put_object"]) == 4
    elif asd == "ASD66":
        text = source_text()
        assert 'retries={"total_max_attempts": 1, "mode": "standard"}' in text
    elif asd == "ASD67":
        runtime, genesis = append_genesis()
        service, private, kms, sts, s3, order = runtime
        seen = []
        service.sleeper = lambda attempt: seen.append(attempt)
        s3.put_faults.append(FakeAwsError(409, "OperationAborted"))
        service.handle(prepared_request(genesis["head"]), invocation=invocation())
        assert seen == [1]
    elif asd == "ASD68":
        runtime, genesis = append_genesis()
        service, private, kms, sts, s3, order = runtime
        before = len([x for x in s3.calls if x[0] == "put_object"])
        expect_code("INSUFFICIENT_RECONCILIATION_BUDGET", lambda: service.handle(prepared_request(genesis["head"]), invocation=invocation(remaining=4000)))
        after = len([x for x in s3.calls if x[0] == "put_object"])
        assert before == after
    elif asd == "ASD69":
        runtime, event = _fresh_append_for_fault("timeout_after_write")
        runtime[0].handle(event, invocation=invocation())
        calls = [name for name, _ in runtime[4].calls]
        put = max(i for i, name in enumerate(calls) if name == "put_object")
        assert "get_object" in calls[put + 1:]
    elif asd == "ASD70":
        service, private, kms, sts, s3, order = make_runtime()
        response = service.handle(common("READ_HEAD"), invocation=invocation())
        assert response["head"]["sequence"] == 0
        assert not [x for x in s3.calls if x[0] == "put_object"]
        assert "mutable authoritative HEAD" not in source_text()
    elif asd == "ASD71":
        service, private, kms, sts, s3, order = make_runtime()
        load_parity_chain(s3)
        del s3.objects[config().receipt_key(2)]
        expect_code("SEQUENCE_GAP_OR_DUPLICATE", lambda: service.handle(common("READ_HEAD"), invocation=invocation()))
    elif asd == "ASD72":
        service, private, kms, sts, s3, order = make_runtime()
        load_parity_chain(s3)
        event = common("READ_RECEIPT")
        event["sequence"] = 3
        response = service.handle(event, invocation=invocation())
        assert response["receipt"]["root_sequence"] == 3
        assert response["head"]["sequence"] == 6
    elif asd == "ASD73":
        text = source_text().lower()
        assert "lru_cache" not in text
        assert "_head_cache" not in text
        assert "_authoritative_cache" not in text
    elif asd == "ASD74":
        runtime, response = append_genesis()
        assert response["schema"] == auth.RESPONSE_SCHEMA
        assert response["status"] in {"APPENDED", "IDEMPOTENT_EXISTING", "IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME"}
        assert set(response["attempts"]) == {"kms_describe", "kms_get_public_key", "kms_sign", "sts_assume_role", "s3_list", "s3_get", "s3_put", "total"}
    elif asd == "ASD75":
        runtime, response = append_genesis()
        raw = json.dumps(response)
        for forbidden in ("FAKE_SECRET", "FAKE_SESSION", "SecretAccessKey", "SessionToken", "AccessKeyId"):
            assert forbidden not in raw
    elif asd == "ASD76":
        assert REQUIREMENTS_PATH.is_file()
        root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        assert "boto3" not in root_requirements and "botocore" not in root_requirements
    elif asd == "ASD77":
        req = requirements_text()
        assert "boto3==1.43.73" in req
        assert "botocore==1.43.73" in req
    elif asd == "ASD78":
        assert "cryptography==50.0.0" in requirements_text()
    elif asd == "ASD79":
        doc = impl_doc_text()
        assert "DEPLOYMENT_PACKAGE_BUILT=FALSE" in doc
        assert "transitive hash lock" in doc.lower()
        assert "SBOM" in doc
    elif asd == "ASD80":
        values = config().__dict__.copy()
        values["signing_key_arn"] = "arn:aws-us-gov:kms:us-gov-west-1:111111111111:key/abcd"
        expect_code("KMS_ARN_INVALID", lambda: auth.AuthorityConfig(**values))
    elif asd == "ASD81":
        text = source_text()
        assert "provider_network_binding" not in text
        assert "SPORTS_PROVIDER" not in text
        assert "authority permit" in impl_doc_text().lower()
    elif asd == "ASD82":
        runtime, response = append_genesis()
        assert response["controlled_live_admissible"] is False
        assert response["stronger_external_authority_implemented"] is False
        assert response["production_admissible"] is False
    elif asd == "ASD83":
        doc = impl_doc_text()
        for token in (
            "REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE",
            "REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE",
            "RESOURCE_PROVISIONING_PERFORMED=FALSE",
            "DEPLOYMENT_PACKAGE_BUILD_AUTHORIZED=FALSE",
        ):
            assert token in doc
    elif asd == "ASD84":
        doc = impl_doc_text()
        assert "MACROBLOCK_2_CLOSED=FALSE" in doc
        assert "REMAINING_C2_LIVE_MACROBLOCKS=5" in doc
    else:
        raise AssertionError(asd)

def env_map(**changes):
    values = {
        "MATRIX_ARCHIVE_ACCOUNT_ID": ARCHIVE_ACCOUNT,
        "MATRIX_ARCHIVE_APPEND_ROLE_NAME": ROLE,
        "MATRIX_ARCHIVE_BUCKET": BUCKET,
        "MATRIX_ARCHIVE_REGION": REGION,
        "MATRIX_AUTHORITY_CODE_SHA256": "a" * 64,
        "MATRIX_AUTHORITY_PROFILE": auth.AUTHORITY_PROFILE,
        "MATRIX_DATABASE_INSTANCE_ID": DB_ID,
        "MATRIX_KEY_EPOCH": "1",
        "MATRIX_PROJECT_DOMAIN_ID": auth.PROJECT_DOMAIN_ID,
        "MATRIX_RECEIPT_PROTOCOL": auth.RECEIPT_PROTOCOL,
        "MATRIX_RESEARCH_ONLY": "true",
        "MATRIX_ROOT_STORE_ID": ROOT_ID,
        "MATRIX_SIGNING_KEY_ARN": KMS_ARN,
        "MATRIX_SPORT_ID": auth.SPORT_ID,
    }
    values.update(changes)
    return values


def _resign_from_payload(payload, private):
    unsigned = {
        key: payload[key]
        for key in (
            "domain_separator", "root_sequence", "previous_receipt_id",
            "previous_receipt_sha256", "receipt_type", "operation_id",
            "project_domain_id", "sport_id", "database_instance_id",
            "control_id", "run_id", "local_transition_event_id",
            "local_transition_event_sha256", "local_transition_sequence",
            "local_control_state_version", "local_schema_user_version",
            "receipt_protocol_version", "created_at", "signer_key_id",
            "root_store_id", "metadata",
        )
    }
    payload_sha = auth._sha(unsigned)
    sig = private.sign(auth._canonical_bytes(unsigned))
    sig_b64 = base64.b64encode(sig).decode("ascii")
    payload["canonical_payload_sha256"] = payload_sha
    payload["signature_b64"] = sig_b64
    payload["receipt_id"] = auth._sha({
        "schema": auth.RECEIPT_ID_SCHEMA,
        "canonical_payload_sha256": payload_sha,
        "signature_b64": sig_b64,
    })
    return auth._canonical_bytes(payload)



def forged_semantic_prepared_raw(genesis_response, kms):
    event = prepared_request(genesis_response["head"])
    intent = event["receipt_intent"]
    key_id = "ed25519:" + hashlib.sha256(kms.raw).hexdigest()
    unsigned = {
        "domain_separator": auth.RECEIPT_DOMAIN_SEPARATOR,
        "root_sequence": 2,
        "previous_receipt_id": genesis_response["head"]["receipt_id"],
        "previous_receipt_sha256": genesis_response["head"]["receipt_sha256"],
        "receipt_type": "ROOT_PREPARED",
        "operation_id": intent["operation_id"],
        "project_domain_id": auth.PROJECT_DOMAIN_ID,
        "sport_id": auth.SPORT_ID,
        "database_instance_id": DB_ID,
        "control_id": intent["control_id"],
        "run_id": intent["run_id"],
        "local_transition_event_id": intent["local_transition_event_id"],
        "local_transition_event_sha256": intent["local_transition_event_sha256"],
        "local_transition_sequence": intent["local_transition_sequence"],
        "local_control_state_version": intent["local_control_state_version"],
        "local_schema_user_version": 87,
        "receipt_protocol_version": 1,
        "created_at": "2026-08-25T23:00:01+00:00",
        "signer_key_id": key_id,
        "root_store_id": ROOT_ID,
        "metadata": dict(intent["metadata"]),
    }
    payload_sha = auth._sha(unsigned)
    signature_b64 = base64.b64encode(b"x" * 64).decode("ascii")
    receipt_id = auth._sha({
        "schema": auth.RECEIPT_ID_SCHEMA,
        "canonical_payload_sha256": payload_sha,
        "signature_b64": signature_b64,
    })
    storage = {
        **unsigned,
        "canonical_payload_sha256": payload_sha,
        "signature_b64": signature_b64,
        "receipt_id": receipt_id,
    }
    # Structural/canonical parsing succeeds; cryptographic chain validation must fail.
    raw = auth._canonical_bytes(storage)
    auth.AuthorityReceipt.from_bytes(raw)
    return raw


def _assert_adv(case):
    if case == 1:
        static_no_top_level_boto_import()
        module = ast.parse(source_text())
        assert any(isinstance(n, ast.FunctionDef) and n.name == "build_real_service" for n in module.body)
    elif case == 2:
        import builtins
        original_import = builtins.__import__
        def blocked(name, *args, **kwargs):
            if name == "boto3" or name.startswith("botocore"):
                raise ImportError("blocked for deterministic offline test")
            return original_import(name, *args, **kwargs)
        builtins.__import__ = blocked
        try:
            expect_code("RUNTIME_DEPENDENCIES_UNAVAILABLE", lambda: auth.build_real_service(env=env_map()))
        finally:
            builtins.__import__ = original_import
    elif case == 3:
        req = requirements_text().splitlines()
        assert "cryptography==50.0.0" in req
        assert "boto3==1.43.73" in req and "botocore==1.43.73" in req
    elif case == 4:
        compile(source_text(), str(SOURCE_PATH), "exec")
        assert "python3.12" in impl_doc_text()
    elif case == 5:
        unqualified = f"arn:aws:lambda:{REGION}:{SIGNING_ACCOUNT}:function:matrix-r836-authority"
        expect_code("GOVERNED_ALIAS_REQUIRED", lambda: invocation(arn=unqualified).validate_for(config()))
    elif case == 6:
        expect_code("RESEARCH_ONLY_REQUIRED", lambda: auth.AuthorityConfig.from_environ(env_map(MATRIX_RESEARCH_ONLY="false")))
    elif case == 7:
        bad = env_map()
        del bad["MATRIX_ROOT_STORE_ID"]
        expect_code("CONFIG_REQUIRED", lambda: auth.AuthorityConfig.from_environ(bad))
        assert "dict(os.environ)" not in source_text()
    elif case == 8:
        event = genesis_request()
        event["receipt_intent"]["metadata"]["backend_profile"] = "CALLER_VALUE"
        expect_code("GENESIS_METADATA_SCHEMA_MISMATCH", lambda: auth.parse_request(event, config()))
    elif case == 9:
        runtime, genesis = append_genesis()
        service = runtime[0]
        service.clock = lambda: datetime(2026, 8, 25, 22, 59, tzinfo=UTC)
        expect_code("RECEIPT_TIME_REGRESSION", lambda: service.handle(prepared_request(genesis["head"]), invocation=invocation()))
    elif case == 10:
        runtime, genesis = append_genesis()
        service = runtime[0]
        prepared = service.handle(prepared_request(genesis["head"]), invocation=invocation())
        event = committed_request(prepared["head"], prepared)
        event["receipt_intent"]["metadata"]["prepared_receipt_id"] = "f" * 64
        expect_code("TERMINAL_PREPARE_BINDING_MISMATCH", lambda: service.handle(event, invocation=invocation()))
    elif case == 11:
        service, private, kms, sts, s3, order = make_runtime()
        prefix = config().receipt_prefix
        for i in range(1, 1002):
            s3.objects[f"{prefix}{i:020d}.json"] = b"x"
        s3.page_size = 1000
        attempts = auth.AttemptCounter()
        seqs = service._list_sequences(s3=s3, attempts=attempts, invocation=invocation())
        assert len(seqs) == 1001 and attempts.s3_list == 2
    elif case == 12:
        service, private, kms, sts, s3, order = make_runtime()
        s3.objects[config().receipt_key(1)] = b"x" * (auth.MAX_RECEIPT_BYTES + 1)
        expect_code("RECEIPT_TOO_LARGE", lambda: service._get_receipt(s3=s3, sequence=1, attempts=auth.AttemptCounter(), invocation=invocation()))
    elif case == 13:
        service, private, kms, sts, s3, order = make_runtime()
        service.handle(common("READ_HEAD"), invocation=invocation())
        call = sts.calls[0]
        assert call["DurationSeconds"] == 900
        assert call["RoleSessionName"].startswith("matrix-r836-")
        assert "req-1" not in call["RoleSessionName"]
    elif case == 14:
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"wrong-sign-id").digest())
        kms = FakeKms(private)
        kms.sign_override = {
            "KeyId": "wrong",
            "SigningAlgorithm": "ED25519_SHA_512",
            "Signature": private.sign(b"x"),
        }
        service, private, kms, sts, s3, order = make_runtime(private=private, kms=kms)
        expect_code("KMS_SIGN_KEY_IDENTITY_MISMATCH", lambda: service.handle(genesis_request(), invocation=invocation()))
    elif case == 15:
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"wrong-public-alg").digest())
        kms = FakeKms(private)
        kms.public_override = {
            "KeyId": KMS_ARN.split("/")[-1],
            "KeySpec": "ECC_NIST_EDWARDS25519",
            "KeyUsage": "SIGN_VERIFY",
            "SigningAlgorithms": ["ECDSA_SHA_256"],
            "PublicKey": kms.der,
        }
        service, private, kms, sts, s3, order = make_runtime(private=private, kms=kms)
        expect_code("KMS_SIGNING_ALGORITHM_MISMATCH", lambda: service.handle(genesis_request(), invocation=invocation()))
    elif case == 16:
        runtime, response = append_genesis()
        attempts = response["attempts"]
        assert attempts["total"] == sum(attempts[k] for k in attempts if k != "total")
    elif case == 17:
        original = auth.build_real_service
        auth.build_real_service = lambda **kwargs: (_ for _ in ()).throw(ValueError("RAW_EXCEPTION_SECRET"))
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                response = auth.handler({"request_nonce": "corr-1", "secret": "USER_SECRET"}, type("C", (), {
                    "invoked_function_arn": INVOKED_ARN,
                    "get_remaining_time_in_millis": lambda self: 30000,
                })())
        finally:
            auth.build_real_service = original
        serialized = json.dumps(response) + out.getvalue()
        assert "RAW_EXCEPTION_SECRET" not in serialized and "USER_SECRET" not in serialized
    elif case == 18:
        text = source_text().lower()
        for forbidden in ("betplay", "betano", "bwin", "provider_api_key", "sports_provider_permit"):
            assert forbidden not in text
    elif case == 19:
        raw = base64.b64decode(PARITY_RECEIPTS_B64[0])
        payload = json.loads(raw)
        payload["unknown"] = 1
        expect_code("RECEIPT_SCHEMA_MISMATCH", lambda: auth.AuthorityReceipt.from_bytes(auth._canonical_bytes(payload)))
    elif case == 20:
        raw = base64.b64decode(PARITY_RECEIPTS_B64[0])
        expect_code("RECEIPT_CANONICAL_BYTES_MISMATCH", lambda: auth.AuthorityReceipt.from_bytes(raw + b" "))
    elif case == 21:
        raw = base64.b64decode(PARITY_RECEIPTS_B64[0])
        payload = json.loads(raw)
        payload["signature_b64"] = base64.b64encode(b"x" * 64).decode("ascii")
        # Recompute receipt id so only signature verification, not id mismatch, detects it.
        payload["receipt_id"] = auth._sha({
            "schema": auth.RECEIPT_ID_SCHEMA,
            "canonical_payload_sha256": payload["canonical_payload_sha256"],
            "signature_b64": payload["signature_b64"],
        })
        tampered = auth.AuthorityReceipt.from_bytes(auth._canonical_bytes(payload))
        expect_code("RECEIPT_SIGNATURE_INVALID", lambda: auth.verify_receipt_chain([tampered], expected_root_store_id=ROOT_ID, expected_database_instance_id=DB_ID))
    elif case == 22:
        receipts = parity_receipts()[:2]
        second_payload = json.loads(receipts[1].canonical_bytes())
        second_payload["previous_receipt_id"] = "f" * 64
        raw = _resign_from_payload(second_payload, Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"MATRIX-R8.3R6-AUTHORITY-PARITY-OLD").digest()))
        second = auth.AuthorityReceipt.from_bytes(raw)
        expect_code("PREDECESSOR_ID_MISMATCH", lambda: auth.verify_receipt_chain([receipts[0], second], expected_root_store_id=ROOT_ID, expected_database_instance_id=DB_ID))
    elif case == 23:
        service, private, kms, sts, s3, order = make_runtime()
        prefix = config().receipt_prefix
        s3.objects[f"{prefix}00000000000000000001.json"] = b"x"
        s3.objects[f"{prefix}00000000000000000003.json"] = b"x"
        expect_code("SEQUENCE_GAP_OR_DUPLICATE", lambda: service._list_sequences(s3=s3, attempts=auth.AttemptCounter(), invocation=invocation()))
    elif case == 24:
        service, private, kms, sts, s3, order = make_runtime()
        s3.objects[config().receipt_prefix + "not-a-receipt"] = b"x"
        expect_code("LIST_KEY_FORMAT_INVALID", lambda: service._list_sequences(s3=s3, attempts=auth.AttemptCounter(), invocation=invocation()))
    elif case == 25:
        runtime, genesis = append_genesis()
        service, private, kms, sts, s3, order = runtime
        event = prepared_request(genesis["head"])
        s3.put_faults.append("tamper_after_write")
        expect_code("RECEIPT_SCHEMA_MISMATCH", lambda: service.handle(event, invocation=invocation()))
    elif case == 26:
        runtime, event = _fresh_append_for_fault("500_after_write")
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME"
        assert response["reconciled"] is True
    elif case == 27:
        runtime, event = _fresh_append_for_fault("409_after_write")
        response = runtime[0].handle(event, invocation=invocation())
        assert response["status"] == "IDEMPOTENT_EXISTING"
    elif case == 28:
        runtime, genesis = append_genesis()
        service, private, kms, sts, s3, order = runtime
        event = prepared_request(genesis["head"])
        # Simulate a same-sequence race that writes a structurally canonical,
        # semantically matching object with an invalid Ed25519 signature.
        s3.race_body = forged_semantic_prepared_raw(genesis, kms)
        s3.put_faults.append("412_with_race_body")
        expect_code("RECEIPT_SIGNATURE_INVALID", lambda: service.handle(event, invocation=invocation()))
    elif case == 29:
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"kms-auth").digest())
        order = []
        kms = FakeKms(private, call_order=order)
        kms.describe_override = FakeAwsError(403, "AccessDenied")
        sts = FakeSts(call_order=order)
        service, *_ = make_runtime(private=private, kms=kms, sts=sts, call_order=order)
        expect_code("AWS_AUTHORIZATION_FAILED", lambda: service.handle(genesis_request(), invocation=invocation()))
        assert "sts:AssumeRole" not in order
    elif case == 30:
        sts = FakeSts()
        sts.error = FakeAwsError(403, "AccessDenied")
        service, private, kms, sts, s3, order = make_runtime(sts=sts)
        expect_code("AWS_AUTHORIZATION_FAILED", lambda: service.handle(common("READ_HEAD"), invocation=invocation()))
        assert not s3.calls
    elif case == 31:
        s3 = FakeS3()
        s3.list_faults.append(FakeAwsError(403, "AccessDenied"))
        service, private, kms, sts, s3, order = make_runtime(s3=s3)
        expect_code("AWS_AUTHORIZATION_FAILED", lambda: service.handle(common("READ_HEAD"), invocation=invocation()))
        assert len([x for x in s3.calls if x[0] == "list_objects_v2"]) == 1
    elif case == 32:
        event = genesis_request()
        event["receipt_intent"]["metadata"]["genesis_transition_events"] = [
            {"run_id": "a"*64, "transition_sequence": i+1, "event_id": "b"*64, "event_sha256": "c"*64}
            for i in range(10001)
        ]
        expect_code("JSON_ARRAY_TOO_LARGE", lambda: auth.parse_request(event, config()))
    elif case == 33:
        event = genesis_request()
        event["receipt_intent"]["metadata"]["genesis_run_state"] = [1.25]
        expect_code("JSON_TYPE_UNSUPPORTED", lambda: auth.parse_request(event, config()))
    elif case == 34:
        service, private, kms, sts, s3, order = make_runtime()
        load_parity_chain(s3)
        s3.force_content_length = 1
        expect_code("CONTENT_LENGTH_MISMATCH", lambda: service.handle(common("READ_HEAD"), invocation=invocation()))
    elif case == 35:
        service, private, kms, sts, s3, order = make_runtime()
        load_parity_chain(s3)
        event = common("APPEND_RECEIPT")
        last = parity_receipts()[-1]
        event["expected_head"] = {
            "sequence": last.root_sequence,
            "receipt_id": last.receipt_id,
            "receipt_sha256": last.receipt_sha256,
        }
        event["receipt_intent"] = prepared_request(event["expected_head"])["receipt_intent"]
        event["receipt_intent"]["operation_id"] = "e" * 64
        expect_code("ACTIVE_SIGNING_KEY_MISMATCH", lambda: service.handle(event, invocation=invocation()))
    elif case == 36:
        runtime, first = append_genesis()
        service, private, kms, sts, s3, order = runtime
        sign_before = len([x for x in kms.calls if x[0] == "sign"])
        put_before = len([x for x in s3.calls if x[0] == "put_object"])
        second = service.handle(genesis_request(), invocation=invocation())
        assert second["status"] == "IDEMPOTENT_EXISTING"
        assert len([x for x in kms.calls if x[0] == "sign"]) == sign_before
        assert len([x for x in s3.calls if x[0] == "put_object"]) == put_before
        assert len([x for x in kms.calls if x[0] == "describe_key"]) >= 2
        assert len(sts.calls) >= 2
    elif case == 37:
        module = ast.parse(source_text())
        authority_class = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "AuthorityService"
        )
        put_receipt = next(
            node
            for node in authority_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_put_receipt"
        )
        retry_loop = next(node for node in ast.walk(put_receipt) if isinstance(node, ast.For))
        statements = [ast.dump(node, include_attributes=False) for node in retry_loop.body]
        guard_index = next(
            index
            for index, statement in enumerate(statements)
            if "_remaining_guard" in statement and "mutation" in statement
        )
        put_index = next(
            index for index, statement in enumerate(statements) if "put_object" in statement
        )
        assert guard_index < put_index
    elif case in {38, 39, 40}:
        runtime, genesis = append_genesis()
        service, private, kms, sts, s3, order = runtime
        baseline_puts = len([x for x in s3.calls if x[0] == "put_object"])
        if case == 38:
            s3.put_faults.append(FakeAwsError(409, "OperationAborted"))
        elif case == 39:
            s3.put_faults.append(FakeAwsError(500, "InternalError"))
        else:
            s3.put_faults.append("timeout_before_write")

        def remaining():
            puts = len([x for x in s3.calls if x[0] == "put_object"])
            return 1000 if puts > baseline_puts else 6000

        dynamic_invocation = auth.InvocationMetadata(INVOKED_ARN, remaining)
        expect_code(
            "INSUFFICIENT_RECONCILIATION_BUDGET",
            lambda: service.handle(
                prepared_request(genesis["head"]),
                invocation=dynamic_invocation,
            ),
        )
        assert len([x for x in s3.calls if x[0] == "put_object"]) == baseline_puts + 1
    else:
        raise AssertionError(case)

def test_asd01_contract():
    _assert_asd("ASD01")

def test_asd02_contract():
    _assert_asd("ASD02")

def test_asd03_contract():
    _assert_asd("ASD03")

def test_asd04_contract():
    _assert_asd("ASD04")

def test_asd05_contract():
    _assert_asd("ASD05")

def test_asd06_contract():
    _assert_asd("ASD06")

def test_asd07_contract():
    _assert_asd("ASD07")

def test_asd08_contract():
    _assert_asd("ASD08")

def test_asd09_contract():
    _assert_asd("ASD09")

def test_asd10_contract():
    _assert_asd("ASD10")

def test_asd11_contract():
    _assert_asd("ASD11")

def test_asd12_contract():
    _assert_asd("ASD12")

def test_asd13_contract():
    _assert_asd("ASD13")

def test_asd14_contract():
    _assert_asd("ASD14")

def test_asd15_contract():
    _assert_asd("ASD15")

def test_asd16_contract():
    _assert_asd("ASD16")

def test_asd17_contract():
    _assert_asd("ASD17")

def test_asd18_contract():
    _assert_asd("ASD18")

def test_asd19_contract():
    _assert_asd("ASD19")

def test_asd20_contract():
    _assert_asd("ASD20")

def test_asd21_contract():
    _assert_asd("ASD21")

def test_asd22_contract():
    _assert_asd("ASD22")

def test_asd23_contract():
    _assert_asd("ASD23")

def test_asd24_contract():
    _assert_asd("ASD24")

def test_asd25_contract():
    _assert_asd("ASD25")

def test_asd26_contract():
    _assert_asd("ASD26")

def test_asd27_contract():
    _assert_asd("ASD27")

def test_asd28_contract():
    _assert_asd("ASD28")

def test_asd29_contract():
    _assert_asd("ASD29")

def test_asd30_contract():
    _assert_asd("ASD30")

def test_asd31_contract():
    _assert_asd("ASD31")

def test_asd32_contract():
    _assert_asd("ASD32")

def test_asd33_contract():
    _assert_asd("ASD33")

def test_asd34_contract():
    _assert_asd("ASD34")

def test_asd35_contract():
    _assert_asd("ASD35")

def test_asd36_contract():
    _assert_asd("ASD36")

def test_asd37_contract():
    _assert_asd("ASD37")

def test_asd38_contract():
    _assert_asd("ASD38")

def test_asd39_contract():
    _assert_asd("ASD39")

def test_asd40_contract():
    _assert_asd("ASD40")

def test_asd41_contract():
    _assert_asd("ASD41")

def test_asd42_contract():
    _assert_asd("ASD42")

def test_asd43_contract():
    _assert_asd("ASD43")

def test_asd44_contract():
    _assert_asd("ASD44")

def test_asd45_contract():
    _assert_asd("ASD45")

def test_asd46_contract():
    _assert_asd("ASD46")

def test_asd47_contract():
    _assert_asd("ASD47")

def test_asd48_contract():
    _assert_asd("ASD48")

def test_asd49_contract():
    _assert_asd("ASD49")

def test_asd50_contract():
    _assert_asd("ASD50")

def test_asd51_contract():
    _assert_asd("ASD51")

def test_asd52_contract():
    _assert_asd("ASD52")

def test_asd53_contract():
    _assert_asd("ASD53")

def test_asd54_contract():
    _assert_asd("ASD54")

def test_asd55_contract():
    _assert_asd("ASD55")

def test_asd56_contract():
    _assert_asd("ASD56")

def test_asd57_contract():
    _assert_asd("ASD57")

def test_asd58_contract():
    _assert_asd("ASD58")

def test_asd59_contract():
    _assert_asd("ASD59")

def test_asd60_contract():
    _assert_asd("ASD60")

def test_asd61_contract():
    _assert_asd("ASD61")

def test_asd62_contract():
    _assert_asd("ASD62")

def test_asd63_contract():
    _assert_asd("ASD63")

def test_asd64_contract():
    _assert_asd("ASD64")

def test_asd65_contract():
    _assert_asd("ASD65")

def test_asd66_contract():
    _assert_asd("ASD66")

def test_asd67_contract():
    _assert_asd("ASD67")

def test_asd68_contract():
    _assert_asd("ASD68")

def test_asd69_contract():
    _assert_asd("ASD69")

def test_asd70_contract():
    _assert_asd("ASD70")

def test_asd71_contract():
    _assert_asd("ASD71")

def test_asd72_contract():
    _assert_asd("ASD72")

def test_asd73_contract():
    _assert_asd("ASD73")

def test_asd74_contract():
    _assert_asd("ASD74")

def test_asd75_contract():
    _assert_asd("ASD75")

def test_asd76_contract():
    _assert_asd("ASD76")

def test_asd77_contract():
    _assert_asd("ASD77")

def test_asd78_contract():
    _assert_asd("ASD78")

def test_asd79_contract():
    _assert_asd("ASD79")

def test_asd80_contract():
    _assert_asd("ASD80")

def test_asd81_contract():
    _assert_asd("ASD81")

def test_asd82_contract():
    _assert_asd("ASD82")

def test_asd83_contract():
    _assert_asd("ASD83")

def test_asd84_contract():
    _assert_asd("ASD84")

def test_hardening_01_adversarial():
    _assert_adv(1)

def test_hardening_02_adversarial():
    _assert_adv(2)

def test_hardening_03_adversarial():
    _assert_adv(3)

def test_hardening_04_adversarial():
    _assert_adv(4)

def test_hardening_05_adversarial():
    _assert_adv(5)

def test_hardening_06_adversarial():
    _assert_adv(6)

def test_hardening_07_adversarial():
    _assert_adv(7)

def test_hardening_08_adversarial():
    _assert_adv(8)

def test_hardening_09_adversarial():
    _assert_adv(9)

def test_hardening_10_adversarial():
    _assert_adv(10)

def test_hardening_11_adversarial():
    _assert_adv(11)

def test_hardening_12_adversarial():
    _assert_adv(12)

def test_hardening_13_adversarial():
    _assert_adv(13)

def test_hardening_14_adversarial():
    _assert_adv(14)

def test_hardening_15_adversarial():
    _assert_adv(15)

def test_hardening_16_adversarial():
    _assert_adv(16)

def test_hardening_17_adversarial():
    _assert_adv(17)

def test_hardening_18_adversarial():
    _assert_adv(18)

def test_hardening_19_adversarial():
    _assert_adv(19)

def test_hardening_20_adversarial():
    _assert_adv(20)

def test_hardening_21_adversarial():
    _assert_adv(21)

def test_hardening_22_adversarial():
    _assert_adv(22)

def test_hardening_23_adversarial():
    _assert_adv(23)

def test_hardening_24_adversarial():
    _assert_adv(24)

def test_hardening_25_adversarial():
    _assert_adv(25)

def test_hardening_26_adversarial():
    _assert_adv(26)

def test_hardening_27_adversarial():
    _assert_adv(27)

def test_hardening_28_adversarial():
    _assert_adv(28)

def test_hardening_29_adversarial():
    _assert_adv(29)

def test_hardening_30_adversarial():
    _assert_adv(30)

def test_hardening_31_adversarial():
    _assert_adv(31)

def test_hardening_32_adversarial():
    _assert_adv(32)

def test_hardening_33_adversarial():
    _assert_adv(33)

def test_hardening_34_adversarial():
    _assert_adv(34)

def test_hardening_35_adversarial():
    _assert_adv(35)

def test_hardening_36_adversarial():
    _assert_adv(36)

def test_hardening_37_mutating_retry_guard_inside_loop():
    _assert_adv(37)

def test_hardening_38_retry_reserve_after_409():
    _assert_adv(38)

def test_hardening_39_retry_reserve_after_5xx():
    _assert_adv(39)

def test_hardening_40_retry_reserve_after_timeout():
    _assert_adv(40)

