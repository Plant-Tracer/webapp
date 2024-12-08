import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles


templates = Jinja2Templates(directory='templates')

async def homepage(request):
    return templates.TemplateResponse(request, 'index.html')

routes = [
    Route('/', endpoint=homepage),
    Mount('/static', StaticFiles(directory='static'), name='static')
]

app = Starlette(debug=True, routes=routes)
if __name__ == "__main__":
    uvicorn.run("s2:app", port=8000, reload=True)
