Gadgets
=======

This is a collection of scripts that I use.


Installation
------------

Copy them into your `$PATH` and add this at the end your `~/.zshrc`

```
if [[ $1 == eval ]]
then
	shift
	"$@"
	set --
fi
```
