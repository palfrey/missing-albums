import amazonproduct
from lxml import etree

# AWS, then SECRET
keys = [x.strip() for x in file(".amazonkey").readlines()]
amazon = amazonproduct.API(keys[0], keys[1], "uk")

def searchByTitle(artist, album):
	ret = {}
	data = amazon.item_search("Music", Artist=artist, Title=album, ResponseGroup="Small,ItemAttributes,Images,OfferSummary")

	open("dump","w").write(etree.tostring(data.Items.Item, pretty_print=True))
	binding = data.Items.Item.ItemAttributes.Binding
	assert binding == "Audio CD", binding

	ret["title"] = data.Items.Item.ItemAttributes.Title
	ret["url"] = data.Items.Item.DetailPageURL
	ret["image"] = data.Items.Item.LargeImage.URL
	ret["lowest_new"] = int(data.Items.Item.OfferSummary.LowestNewPrice.Amount)
	return ret
