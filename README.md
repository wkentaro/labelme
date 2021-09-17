This is an intelligent barcode annotation tool forked from labelme.

## Install

Install dependencies with the following command:

```
pip install -r requirements.txt
```

## Run

```
python __main__.py
```

## Barcode Annotation Relevant Changes

1. A content property is added to the shape object. Users can modify and check the barcode content in the label dialog.
2. The [Dynamsoft Barcode Reader](https://www.dynamsoft.com/barcode-reader/overview/) is used to automatically annotate barcodes.