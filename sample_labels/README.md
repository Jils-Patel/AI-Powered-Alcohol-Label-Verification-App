# Sample test labels

Synthetic label photos for trying out the app locally. Each one exercises a
different verdict path.

## `silver_creek_clean.jpg`
Clean, well-formatted label. Enter these exact application values to see an
all-**Match** result:

| Field | Value |
|---|---|
| Brand Name | `Silver Creek` |
| Class / Type | `Bourbon Whiskey` |
| Alcohol Content | `13.5% ALC/VOL` |
| Net Contents | `750 ML` |
| Producer Info | `Bottled by Silver Creek Distillers, Louisville, KY` |

## `hopwell_formatting_issue.jpg`
Government warning is lowercase and not bold — everything else matches.
Shows the **Needs Review** verdict with specific formatting issues listed.

| Field | Value |
|---|---|
| Brand Name | `Hopwell Brewing` |
| Class / Type | `India Pale Ale` |
| Alcohol Content | `6.2% ALC/VOL` |
| Net Contents | `355 ML` |
| Producer Info | `Brewed by Hopwell Brewing Co., Portland, OR` |

## `silver_creek_blurry.jpg`
Same label as above, but blurred, darkened, and rotated to simulate a bad
phone photo. Most fields come back **Unreadable** (not "Mismatch") with a
low-confidence warning banner — use the same application values as
`silver_creek_clean.jpg` above to see it.

## `old_tom_import.jpg`
An imported spirits label (matches the example in the take-home
instructions), used to test the **Country of Origin** field:

| Field | Value |
|---|---|
| Brand Name | `Old Tom Distillery` |
| Class / Type | `Kentucky Straight Bourbon Whiskey` |
| Alcohol Content | `45% Alc./Vol. (90 Proof)` |
| Net Contents | `750 mL` |
| Producer Info | `Imported by Old Tom Imports, New York, NY` |
| Country of Origin | `Product of Scotland` |

## Batch mode
Upload all four at once in the Batch Upload tab (no manifest needed to see
extraction-only results), or use `label1.jpg` / `label2.jpg` / `label3.jpg`
(identical copies, just renamed) together with `sample_manifest.csv` in this
same folder to see the full auto-filled comparison path.
