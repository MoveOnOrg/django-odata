# Django OData

Incomplete implementation of [Odata](http://docs.oasis-open.org/odata/odata/v4.0/errata03/os/complete/part2-url-conventions/odata-v4.0-errata03-os-part2-url-conventions-complete.html).

I'll take pull requests, though!

```python
import odata

def foo(request):
    odata_filtertext = request.GET.get('$filter')
    if odata_filtertext:
        model_query = odata.django_filter(odata_filtertext)
        MyModel.objects.filter(model_query)
        ...
```

## What's implemented so far:

You'll notice if you're looking for something comprehensive, this isn't it. Odata has
some CRAZY functions a bunch of which don't really map well to the Django ORM anyway.
However, if you're doing 'normal'ish queries, then a lot is supported.

 - [ ] `$filter=`
   - [x] field name lookup
   - [x] Logical Operators (`and`, `or`, `not`) and (`eq`, `ne`, `gt`, `ge`, `lt`, `le`)
   - [x] Date support
   - [x] `contains(name, val)` function
   - [ ] `has` operator
   - [ ] arithmetic operators (addition, subtraction, etc)
   - [ ] other expression functions (`indexof`, `startswith`, `endswith`)
   - [ ] attribute functions (`length`, `concat`, `trim`, `day`, `now`, etc)
   - [ ] `@`variable references
 - [ ] `$orderby=`


## Some filters that will work:

* `start_date gt '2017-03-01'`
* `start_date ge '2017-03-01' and start_date lt '2017-03-02'`
* `location/postal_code eq '22980'`
* `contains(name, 'Sessions') or contains(name, 'DeVos')`
* `location/postal_code eq '22980' and (contains(name, 'Sessions') or contains(name, 'DeVos'))`
* `(contains(name, 'Sessions') or contains(name, 'DeVos')) and location/postal_code eq '22980'`

## More advanced stuff

Check out the code to see what you can do, but some other features include:

* Customize your field mapping (e.g. map `location/addr` to something other than `location__addr`)
* Subclass/replace `odata.DjangoFilterAdapter` and pass that to `odata.FilterProcessor` if you want to use this code to support, e.g. SQLAlchemy or some other orm or query builder.