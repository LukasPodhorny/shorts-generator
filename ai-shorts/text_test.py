# importing editor from movie py
from moviepy import TextClip

# text
text = "GeeksforGeeks"

# creating a text clip
# having font arial-bold
# with font size = 70
# and color = green
clip = TextClip(text=text, font_size=70, color="green")

# showing  clip
