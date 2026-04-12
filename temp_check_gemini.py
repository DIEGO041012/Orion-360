import importlib
names = ['google.generativeai', 'google.genai']
for name in names:
    try:
        mod = importlib.import_module(name)
        print('imported', name, getattr(mod, '__version__', 'unknown'))
        print('has GenerativeModel', hasattr(mod, 'GenerativeModel'))
        if hasattr(mod, 'GenerativeModel'):
            GM = getattr(mod, 'GenerativeModel')
            print('GenerativeModel type', GM)
            print('has generate_content', hasattr(GM, 'generate_content'))
            print('has generate_text', hasattr(GM, 'generate_text'))
    except Exception as e:
        print('failed', name, repr(e))
