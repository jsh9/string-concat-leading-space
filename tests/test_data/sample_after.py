x = (
    'plain one'
    ' two'
)
y = (
    f'value {x} is'  # a comment
    f' {x!r} and'
    r' raw \d'
    ' tail'
)
b = (
    rb'raw bytes'
    rb' tail'
)
z = 'same line ' 'stays'
w = (
    'ends with backslash space \ '
    'next'
)
v = (
    """triple """
    'not touched'
)
u = (
    f'nested {f"inner "}'
    ' end'
)
t = (
    'two spaces'
    '  after'
)
