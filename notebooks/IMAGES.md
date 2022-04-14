# Images that aren't Showing up in the Notebook on Github
 <!-- markdownlint-disable-file MD033 -->

## Create the Inspectors Grid

```python
X, Y, i3d = inspectors_3D_from_dryruns(21, 21)
```

### Scratch Slot #3

```python
blackbox_plot(X, Y, [[inspector.final_scratch().get(3,0) for inspector in row] for row in i3d], title="Scratch Slot #3")
```

<img width="562" alt="image" src="https://user-images.githubusercontent.com/291133/163443705-46db6306-e2f6-4597-9a47-c0ed160a4bc2.png">

### Max Stack Height Analysis

```python
blackbox_plot(X, Y, [[inspector.max_stack_height() for inspector in row] for row in i3d], ztick=None, ztitle="Max Stack Height", title="Max Stack Height Analysis")
```

<img width="559" alt="image" src="https://user-images.githubusercontent.com/291133/163443812-0069ff99-9fd6-4969-adf2-9d632c8071af.png">

### Scratch Slot 0

```python
blackbox_plot(
    X, 
    Y, 
    [[inspector.final_scratch().get(0,0) for inspector in row] for row in i3d], 
    ztick=None, 
    ztitle="Scratch Slot 0",
    title="Slot 0 Analysis"
)
```

<img width="556" alt="image" src="https://user-images.githubusercontent.com/291133/163443964-b89f7652-2cf0-498c-919b-02ceee713614.png">

### Stack Top

```python
blackbox_plot(X, Y, [[inspector.stack_top() for inspector in row] for row in i3d], ztick=None, ztitle="final stack top", title="Stack Top Analysis")
```

<img width="559" alt="image" src="https://user-images.githubusercontent.com/291133/163444098-e957d8b4-4471-4dc4-addf-fb236ee0f4fc.png">

### Payment Transaction

<img width="552" alt="image" src="https://user-images.githubusercontent.com/291133/163444304-d380c1a8-b42d-4b6c-a801-e173a7d994fc.png">
