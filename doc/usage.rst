Usage
-----

Motivated that :mod:`bluesky` wants to iterate over plans while
solvers typically use call backs. This module allows using an
object within the callback to be provided to the solver. Each 
time the solver calls the callback, an object is typically
submitted to :class:`bcib.CallbackIteratorBridge`. 

In a separate 
