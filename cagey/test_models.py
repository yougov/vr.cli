from cagey.models import Build

def test_build_sets():
	"""
	A set of builds should resolve distinct builds
	"""
	b1 = Build(None, {'app': 'foo'})
	b2 = Build(None, {'app': 'foo'})
	b3 = Build(None, {'app': 'bar'})
	assert set([b1, b2, b3]) == set([b1, b3])
