from bottle import route, run, default_app, static_file, request, abort
import sys
import json

from opentapioca.wikidatagraph import WikidataGraph
from opentapioca.languagemodel import BOWLanguageModel
from opentapioca.tagger import Tagger
from opentapioca.classifier import SimpleTagClassifier
from opentapioca.goldstandard import GoldStandardDataset

fname = sys.argv[1]
print('Loading '+fname)
bow = BOWLanguageModel()
bow.load(fname)
print('Loading '+sys.argv[2])
graph = WikidataGraph()
graph.load_pagerank(sys.argv[2])
tagger = Tagger(bow, graph)
print('Loading dataset')
goldstandard = GoldStandardDataset('data/affiliations.tsv')
classifier = None
print('Loading classifier')
classifier = SimpleTagClassifier(tagger)
classifier.load(sys.argv[3])

def jsonp(view):
    """
    Decorator for views that return JSON
    """
    def wrapped(*posargs, **kwargs):
        args = {}
        # if we access the args via get(),
        # we can get encoding errors...
        for k in request.forms:
            args[k] = getattr(request.forms, k)
        for k in request.query:
            args[k] = getattr(request.query, k)
        callback = args.get('callback')
        status_code = 200
        try:
            result = view(args, *posargs, **kwargs)
        except (KeyError) as e:#ValueError, AttributeError, KeyError) as e:
            import traceback, sys
            traceback.print_exc(file=sys.stdout)
            result = {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}
            status_code = 403
        if callback:
            result = '%s(%s);' % (callback, json.dumps(result))

        if status_code == 200:
            return result
        else:
            abort(status_code, result)

    return wrapped


@route('/api/annotate', method=['GET','POST'])
@jsonp
def annotate_api(args):
    text = args['query']
    mentions = tagger.tag_and_rank(text)
    if classifier:
        classifier.classify_mentions(mentions)

    return {
        'text':text,
        'annotations': mentions
    }

@route('/api/get_doc', method=['GET'])
@jsonp
def get_doc(args):
    doi, doc = goldstandard.get_unannotated_doi_doc()
    tags = tagger.tag_and_rank(doc)
    return {
        'text': doc,
        'doi': doi,
        'annotations': tags
    }

@route('/api/store_judgments', method=['POST'])
@jsonp
def store_judgments(args):
    doi = args.get('doi')
    if doi:
        doc = args.get('doc')
        judgments = json.loads(args.get('judgments'))
        goldstandard.set_judgments(doi, doc, judgments)
        goldstandard.save()

@route('/')
def home():
    return static_file('index.html', root='html/')

@route('/judge')
def judge():
    return static_file('judge.html', root='html/')

@route('/css/<fname>')
def css(fname):
    return static_file(fname, root='html/css/')

@route('/js/<fname>')
def js(fname):
    return static_file(fname, root='html/js/')

if __name__ == '__main__':
    run(host='0.0.0.0', port=8457, debug=True)

app = application = default_app()