import amazonproduct
from lxml import etree

# AWS, then SECRET, then associate id
keys = [x.strip() for x in file(".amazonkey").readlines()]
amazon = amazonproduct.API(keys[0], keys[1], "uk")

def searchByTitle(artist, album):
	ret = {}
	try:
		root = amazon.item_search("Music", Artist=artist, Title=album, ResponseGroup="Small,ItemAttributes,Images,Offers", AssociateTag = keys[2], MerchantId = "Amazon", Condition = "New")
	except amazonproduct.errors.NoExactMatchesFound:
		ret["title"] = album
		ret["url"] = None
		ret["image"] = None
		ret["amazon_new"] = None
		return ret

	page = root.page(1)

	binding = page.Items.Item.ItemAttributes.Binding
	if binding!="Audio CD":
		file("dump","wb").write(etree.tostring(page, pretty_print=True))
		raise Exception, binding

	ret["title"] = page.Items.Item.ItemAttributes.Title
	ret["url"] = page.Items.Item.DetailPageURL
	ret["image"] = page.Items.Item.LargeImage.URL
	#ret["lowest_new"] = int(page.Items.Item.OfferSummary.LowestNewPrice.Amount)
	ret["amazon_new"] = int(page.Items.Item.Offers.Offer.OfferListing.Price.Amount)
	return ret
