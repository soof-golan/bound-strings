# bound-strings

A highly experimental, insecure, transform from f-strings into a bindable object

**DO NOT USE THIS LIBRARY FOR REAL CODE**

# Elevator Pitch

If all goes well this code:

```python
@bind(SQLQuery)
def my_query(boom):
    return f'SELECT * FROM table WHERE id = {boom}'
```

Behaves like this code:

```python
@bind(SQLQuery)
def my_query(not_so_boom):
    return SQLQuery('SELECT * FROM table WHERE id = $1', not_so_boom)
```

# Why?

I was bored and wanted to see if I could do it.

# More details?

This is a "Security" source code transformation. It allows you to write UNSAFE code
like SQL statements with f-strings variable interpolation (because the UX is nice) and then
transform the f-strings CST (concrete syntax tree) into a Bindable object
of seriously questionable safety.

## What is a Bindable object?

A bindable objects allows you to "bind" the expressions inside an f-string
(the thing between the curly braces `{}`) to a transformed template string.
In this case, the SQLQuery binds args to the template with $1, $2, etc.

Assumption (Which should be challenged):

- What ever consumer you have for the "f-string" object, can accept the new Bindable
  object and be useful with it.

